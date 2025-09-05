import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import structlog
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

# We'll implement web search directly in this service

from app.core.config import settings
from app.models.response_models import NewsAnalysis, NewsArticle, NewsItem, PositiveNews, NegativeNews

logger = structlog.get_logger()


class WebSearch:
    """Production-ready web search using NewsAPI.org for real articles."""
    
    def __init__(self):
        self.timeout = 10
        self.user_agent = "Mozilla/5.0 (compatible; NewsAnalyzer/1.0)"
        self.news_api_key = settings.NEWS_API_KEY
        self.base_url = "https://newsapi.org/v2"
        self.google_api_key = settings.GOOGLE_SEARCH_API_KEY
        self.google_engine_id = settings.GOOGLE_SEARCH_ENGINE_ID
    
    async def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for real news articles using NewsAPI.org.
        Returns list of article dictionaries with title, url, source, date, content.
        """
        try:
            # Extract company name for targeted search
            company_terms = self._extract_company_terms(query)
            
            # Determine search sentiment
            is_positive = any(term in query.lower() for term in ['positive', 'success', 'achievement', 'growth', 'expansion', 'award'])
            is_negative = any(term in query.lower() for term in ['negative', 'problems', 'lawsuit', 'scandal', 'investigation', 'crisis'])
            
            # Build search query for NewsAPI
            search_query = company_terms
            if is_positive:
                search_query += " AND (success OR growth OR award OR achievement OR expansion)"
            elif is_negative:
                search_query += " AND (lawsuit OR scandal OR investigation OR problems OR crisis)"
            
            # ONLY use Google Custom Search - no more fallbacks with fake links
            if self.google_api_key and self.google_engine_id:
                articles = await self._search_google_custom(search_query, max_results)
                # Validate all links are working before returning
                validated_articles = await self._validate_article_links(articles)
                return validated_articles
            
            # If Google Search is not configured, return empty results
            logger.error("Google Custom Search API niet geconfigureerd - geen zoekresultaten beschikbaar")
            return []
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []
    
    async def _search_google_custom(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Search using Google Custom Search API for real articles."""
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.google_api_key,
                "cx": self.google_engine_id,
                "q": query,
                "num": min(max_results, 10),  # Google allows max 10 results per request
                "sort": "date",
                "fileType": "",  # Exclude non-web results
                "siteSearch": "",  # Can be used to search specific sites
            }
            
            # Add Dutch news sites for priority
            dutch_news_sites = "site:fd.nl OR site:nrc.nl OR site:nos.nl OR site:volkskrant.nl OR site:bnr.nl OR site:ad.nl OR site:telegraaf.nl"
            params["q"] = f"{query} ({dutch_news_sites})"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    articles = []
                    
                    for item in data.get("items", []):
                        if item.get("link") and item.get("title"):
                            # Extract snippet as content
                            content = item.get("snippet", "")
                            
                            # Try to extract date from meta tags or snippet
                            published_date = "2024-01-01"  # Default
                            if "metatags" in item.get("pagemap", {}):
                                for meta in item["pagemap"]["metatags"]:
                                    if "article:published_time" in meta:
                                        published_date = meta["article:published_time"][:10]
                                        break
                                    elif "date" in meta:
                                        published_date = meta["date"][:10]
                                        break
                            
                            # Extract source from URL
                            import urllib.parse
                            parsed_url = urllib.parse.urlparse(item["link"])
                            source = parsed_url.netloc.replace("www.", "")
                            
                            articles.append({
                                "title": item["title"],
                                "url": item["link"],
                                "source": source,
                                "date": published_date,
                                "content": content
                            })
                    
                    logger.info(f"Google Custom Search found {len(articles)} articles")
                    return articles[:max_results]
                else:
                    logger.warning(f"Google Custom Search API error: {response.status_code}")
                    
        except Exception as e:
            logger.warning(f"Google Custom Search failed: {e}")
            return []

    async def _search_newsapi(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Search using NewsAPI.org for real articles."""
        try:
            url = f"{self.base_url}/everything"
            params = {
                "q": query,
                "apiKey": self.news_api_key,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": min(max_results, 100),
                "excludeDomains": "reddit.com,twitter.com"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    articles = []
                    
                    for article in data.get("articles", []):
                        if article.get("url") and article.get("title"):
                            articles.append({
                                "title": article["title"],
                                "url": article["url"],
                                "source": article.get("source", {}).get("name", "Unknown"),
                                "date": article.get("publishedAt", "2024-01-01")[:10],
                                "content": article.get("description") or article.get("content", "")[:500]
                            })
                    
                    return articles[:max_results]
                    
        except Exception as e:
            logger.warning(f"NewsAPI search failed: {e}")
            return []
    
    async def _validate_article_links(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate that all article links are working and fetch full content."""
        validated_articles = []
        
        for article in articles:
            url = article.get('url')
            if not url:
                continue
                
            try:
                # Fetch full article content
                full_content = await self._fetch_article_content(url)
                if full_content:
                    # Update article with full content
                    article['content'] = full_content
                    validated_articles.append(article)
                    logger.info(f"Successfully fetched content from: {url}")
                else:
                    logger.warning(f"Could not fetch content from: {url}")
                        
            except Exception as e:
                logger.warning(f"Link validation failed for {url}: {e}")
        
        logger.info(f"Successfully fetched content from {len(validated_articles)} out of {len(articles)} articles")
        return validated_articles

    async def _fetch_article_content(self, url: str) -> str:
        """Fetch and extract the main content from an article URL."""
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            ) as client:
                response = await client.get(url)
                
                if response.status_code != 200:
                    return ""
                
                # Parse HTML content
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                    script.decompose()
                
                # Try to find main content in common article selectors
                content_selectors = [
                    'article',
                    '.article-content',
                    '.article-body', 
                    '.content',
                    '.post-content',
                    '[role="main"]',
                    'main',
                    '.story-content',
                    '.entry-content'
                ]
                
                content_text = ""
                for selector in content_selectors:
                    content_element = soup.select_one(selector)
                    if content_element:
                        content_text = content_element.get_text(separator=' ', strip=True)
                        break
                
                # If no specific content area found, get text from body
                if not content_text:
                    content_text = soup.get_text(separator=' ', strip=True)
                
                # Clean up and limit content length
                content_text = ' '.join(content_text.split())  # Remove extra whitespace
                
                # Limit to reasonable length for OpenAI processing (approximately 3000 words)
                if len(content_text) > 12000:
                    content_text = content_text[:12000] + "..."
                
                return content_text
                
        except Exception as e:
            logger.error(f"Failed to fetch content from {url}: {e}")
            return ""
    
    
    def _extract_company_terms(self, query: str) -> str:
        """Extract main company terms from search query."""
        terms = query.split()
        stopwords = {'news', 'positive', 'negative', 'success', 'problems', 'lawsuit', 'scandal', 'investigation', 'achievements', 'growth', 'expansion'}
        company_terms = ' '.join([term for term in terms if term.lower() not in stopwords])
        return company_terms or "Company"


class NewsService:
    """AI-powered news analysis service using OpenAI."""

    def __init__(self):
        """Initialize the NewsService with OpenAI client."""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            http_client=httpx.Client(timeout=settings.OPENAI_TIMEOUT),
        )
        self.model = "gpt-4.1"  # GPT-4-turbo
        self.temperature = 0.1
        self.max_tokens = 4000
        
        # Token limits
        self.max_input_tokens = 128000  # 128k context
        self.max_output_tokens = 4000
        
        # Simple in-memory cache
        self.cache = {}
        
        # Initialize web search
        self.web_search = WebSearch()
        self.cache_ttl = {}
        
        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0

    async def search_company_news(
        self, company_name: str, search_params: Dict[str, Any], contact_person: str = None
    ) -> NewsAnalysis:
        """
        Search and analyze news about a company.
        
        Args:
            company_name: Name of the company to search for
            search_params: Search parameters (date_range, include_positive, etc.)
            contact_person: Optional contact person name to include in searches
            
        Returns:
            NewsAnalysis with sentiment analysis and relevance scoring
        """
        logger.info("Starting news search", company=company_name, params=search_params)
        
        try:
            # Generate cache key including contact person
            cache_key = self._generate_cache_key(company_name, search_params, contact_person)
            
            # Check cache first
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                logger.info("Returning cached result", company=company_name)
                return NewsAnalysis.model_validate(cached_result)
            
            # Perform news search using OpenAI function calling
            search_results = await self._perform_web_search(company_name, search_params, contact_person)
            
            # Analyze sentiment and relevance for each article
            analyzed_articles = []
            for article in search_results:
                analyzed_article = await self._analyze_article(article, company_name)
                if analyzed_article:
                    analyzed_articles.append(analyzed_article)
            
            # Filter by relevance threshold (lowered from 0.6 to 0.4 for more inclusive results)
            relevant_articles = [
                article for article in analyzed_articles
                if article.relevance_score >= 0.4
            ]
            
            # Backup strategy: ensure minimum articles if strict filtering removes too many
            if len(relevant_articles) < 5 and len(analyzed_articles) > 0:
                # Sort by relevance and take best articles even if below 0.4 threshold
                backup_articles = sorted(analyzed_articles, key=lambda x: x.relevance_score, reverse=True)
                relevant_articles = backup_articles[:min(8, len(backup_articles))]
                
                logger.info(f"Applied backup filtering: included {len(relevant_articles)} articles "
                           f"(minimum relevance: {min(a.relevance_score for a in relevant_articles):.2f})")
            
            # Generate overall analysis
            news_analysis = await self._generate_overall_analysis(
                company_name, relevant_articles
            )
            
            # Cache the result
            self._cache_result(cache_key, news_analysis.model_dump(), ttl_hours=6)
            
            logger.info(
                "News search completed",
                company=company_name,
                total_found=len(search_results),
                relevant=len(relevant_articles)
            )
            
            return news_analysis
            
        except Exception as e:
            logger.error(
                "News search failed",
                company=company_name,
                error=str(e),
                exc_info=True
            )
            # Return empty analysis on error
            empty_positive = PositiveNews(count=0, average_sentiment=0.0, articles=[])
            empty_negative = NegativeNews(count=0, average_sentiment=0.0, articles=[])
            
            return NewsAnalysis(
                positive_news=empty_positive,
                negative_news=empty_negative,
                overall_sentiment=0.0,
                sentiment_summary={"positive": 0, "neutral": 0, "negative": 0},
                total_relevance=0.0,
                total_articles_found=0,
                articles=[],
                key_topics=[],
                risk_indicators=[],
                summary="News analysis failed due to technical issues."
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def _perform_web_search(
        self, company_name: str, search_params: Dict[str, Any], contact_person: str = None
    ) -> List[Dict[str, Any]]:
        """
        Perform actual web search using OpenAI function calling.
        Searches for both positive and negative news about the company.
        """
        date_range = search_params.get("date_range", "6m")
        include_positive = search_params.get("include_positive", True)
        include_negative = search_params.get("include_negative", True)
        
        # Use OpenAI to perform actual web search
        search_results = []
        
        # Build search queries with contact person if provided
        base_query = company_name
        if contact_person:
            # Extract first and last name for more flexible searching
            names = contact_person.strip().split()
            if len(names) >= 2:
                first_name, last_name = names[0], names[-1]
                contact_query = f'{company_name} ("{contact_person}" OR "{first_name} {last_name}" OR "{last_name}")'
            else:
                contact_query = f'{company_name} "{contact_person}"'
        else:
            contact_query = company_name

        # Search for positive news
        if include_positive:
            positive_results = await self._search_web_content(
                f'{base_query} positive news success achievements growth expansion',
                'positive',
                date_range
            )
            search_results.extend(positive_results)
            
            # Additional search with contact person if provided
            if contact_person:
                contact_positive_results = await self._search_web_content(
                    f'{contact_query} success achievement award recognition',
                    'positive',
                    date_range
                )
                search_results.extend(contact_positive_results)
        
        # Search for negative news
        if include_negative:
            negative_results = await self._search_web_content(
                f'{base_query} negative news problems lawsuit scandal investigation',
                'negative', 
                date_range
            )
            search_results.extend(negative_results)
            
            # Additional search with contact person if provided
            if contact_person:
                contact_negative_results = await self._search_web_content(
                    f'{contact_query} lawsuit scandal investigation controversy',
                    'negative',
                    date_range
                )
                search_results.extend(contact_negative_results)
        
        return search_results

    def _generate_search_queries(
        self, company_name: str, date_range: str, include_positive: bool, include_negative: bool
    ) -> List[str]:
        """Generate optimized search queries for the company."""
        base_queries = [
            f'"{company_name}" news',
            f'"{company_name}" company',
        ]
        
        if include_positive:
            positive_queries = [
                f'"{company_name}" award growth expansion success',
                f'"{company_name}" contract deal partnership',
            ]
            base_queries.extend(positive_queries)
        
        if include_negative:
            negative_queries = [
                f'"{company_name}" lawsuit bankruptcy scandal problems',
                f'"{company_name}" investigation fine penalty',
            ]
            base_queries.extend(negative_queries)
        
        return base_queries

    async def _search_web_content(
        self, search_query: str, sentiment_hint: str, date_range: str
    ) -> List[Dict[str, Any]]:
        """
        Use WebSearch to find actual news articles about the company.
        """
        try:
            logger.info(f"Searching web content for: {search_query}")
            
            # Use our WebSearch to get real articles
            articles = await self.web_search.search_news(search_query, max_results=10)
            
            # Convert date strings to datetime objects if needed
            for article in articles:
                if 'date' in article and isinstance(article['date'], str):
                    try:
                        article['date'] = datetime.strptime(article['date'], '%Y-%m-%d')
                    except ValueError:
                        article['date'] = datetime.now()
                elif 'date' not in article:
                    article['date'] = datetime.now()
            
            logger.info(f"Found {len(articles)} articles for query: {search_query}")
            return articles
                
        except Exception as e:
            logger.error(f"Web search failed for query: {search_query}, error: {e}")
            return []

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def _analyze_article(
        self, article: Dict[str, Any], company_name: str
    ) -> Optional[NewsArticle]:
        """Analyze individual article for sentiment and relevance."""
        try:
            # Prepare the enhanced analysis prompt
            system_prompt = """Je bent een Nederlandse business intelligence analist die gespecialiseerd is in bedrijfsreputatie analyse.

Analyseer dit nieuwsartikel en bepaal:
1. Sentiment score (-1.0 tot 1.0, waarbij -1 zeer negatief is, 0 neutraal, 1 zeer positief)
2. Relevantie voor het bedrijf (0.0 tot 1.0, waarbij 0 niet relevant is, 1 zeer relevant)
3. Nederlandse samenvatting (max 200 karakters) van wat er in het artikel staat
4. Classificatie: "goed nieuws" of "slecht nieuws"

BELANGRIJKE INSTRUCTIES VOOR RELEVANTIE:
- Als het bedrijf EXPLICIET genoemd wordt: minimaal 0.6
- Als het bedrijf onderdeel is van de hoofdverhaal: 0.7-0.9  
- Als het artikel grotendeels over het bedrijf gaat: 0.8-1.0
- Als het bedrijf alleen kort genoemd wordt: 0.4-0.5
- Als het bedrijf in de context staat (sector/concurrent): 0.3-0.4
- Alleen als het bedrijf totaal niet relevant is: onder 0.3

Wees MINDER streng met relevantie scoring - Nederlandse bedrijven verdienen meer aandacht.
Focus op bedrijfsgevolgen en wees objectief maar niet te kritisch op relevantie.
Antwoord in geldig JSON formaat met velden: sentiment_score, relevance_score, summary, classification"""

            user_prompt = f"""
Bedrijf: {company_name}
Artikel Titel: {article.get('title', '')}
Bron: {article.get('source', 'Onbekend')}
URL: {article.get('url', '')}

VOLLEDIGE ARTIKEL CONTENT:
{article.get('content', '')[:8000]}

Analyseer dit artikel's sentiment en relevantie voor {company_name}. 
Geef een eerlijke Nederlandse samenvatting van wat er werkelijk in het artikel staat.
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=500,
            )
            
            # Track token usage
            self.total_input_tokens += response.usage.prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens
            self.total_requests += 1
            
            # Parse response
            content = response.choices[0].message.content.strip()
            
            # Try to extract JSON from response
            try:
                # Look for JSON in the response
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx]
                    analysis = json.loads(json_str)
                else:
                    # Fallback parsing
                    analysis = self._parse_analysis_fallback(content)
            except json.JSONDecodeError:
                analysis = self._parse_analysis_fallback(content)
            
            # Validate and create NewsItem
            sentiment_score = max(-1.0, min(1.0, float(analysis.get('sentiment_score', 0.0))))
            relevance_score = max(0.0, min(1.0, float(analysis.get('relevance_score', 0.0))))
            summary = str(analysis.get('summary', article.get('title', '')))[:200]
            classification = analysis.get('classification', 'neutraal nieuws')
            
            # Log the OpenAI analysis for transparency
            logger.info(f"OpenAI Analysis - {company_name}: {classification} (sentiment: {sentiment_score}, relevance: {relevance_score})")
            logger.info(f"Summary: {summary}")
            logger.info(f"URL: {article.get('url', '')}")
            
            return NewsArticle(
                title=article.get('title', ''),
                source=article.get('source', 'Unknown'),
                date=article.get('date', datetime.now()),
                summary=summary,
                sentiment_score=sentiment_score,
                relevance_score=relevance_score,
                url=article.get('url'),
                categories=self._classify_categories(article.get('title', '') + ' ' + summary),
                key_phrases=self._extract_key_phrases_ai(summary),
                trust_score=self._get_trust_score_for_source(article.get('source', ''))
            )
            
        except Exception as e:
            logger.warning(
                "Article analysis failed",
                article_title=article.get('title'),
                error=str(e)
            )
            return None

    def _parse_analysis_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parser for when JSON parsing fails."""
        analysis = {
            'sentiment_score': 0.0,
            'relevance_score': 0.5,
            'summary': content[:200] if content else "Analysis unavailable"
        }
        
        # Try to extract sentiment and relevance from text
        import re
        
        sentiment_match = re.search(r'sentiment[:\s]*(-?[0-9.]+)', content.lower())
        if sentiment_match:
            try:
                analysis['sentiment_score'] = float(sentiment_match.group(1))
            except ValueError:
                pass
        
        relevance_match = re.search(r'relevance[:\s]*([0-9.]+)', content.lower())
        if relevance_match:
            try:
                analysis['relevance_score'] = float(relevance_match.group(1))
            except ValueError:
                pass
        
        return analysis

    def _classify_categories(self, text: str) -> List[str]:
        """Classify article into business categories."""
        categories = []
        text_lower = text.lower()
        
        # Financial category
        financial_keywords = ['financial', 'revenue', 'profit', 'loss', 'earnings', 'quarterly', 'winst', 'omzet', 'financieel']
        if any(keyword in text_lower for keyword in financial_keywords):
            categories.append('financial')
        
        # Legal category
        legal_keywords = ['lawsuit', 'court', 'legal', 'investigation', 'rechtszaak', 'juridisch', 'onderzoek']
        if any(keyword in text_lower for keyword in legal_keywords):
            categories.append('legal')
        
        # Operational category
        operational_keywords = ['operations', 'business', 'expansion', 'growth', 'development', 'bedrijfsvoering', 'operaties']
        if any(keyword in text_lower for keyword in operational_keywords):
            categories.append('operational')
        
        # Regulatory category
        regulatory_keywords = ['regulatory', 'compliance', 'fine', 'penalty', 'regelgeving', 'boete']
        if any(keyword in text_lower for keyword in regulatory_keywords):
            categories.append('regulatory')
        
        # Innovation category
        innovation_keywords = ['innovation', 'technology', 'digital', 'tech', 'innovatie', 'technologie']
        if any(keyword in text_lower for keyword in innovation_keywords):
            categories.append('innovation')
        
        return categories if categories else ['general']

    def _extract_key_phrases_ai(self, text: str) -> List[str]:
        """Extract key phrases using AI-enhanced method."""
        # For now, use the simple method but could be enhanced with OpenAI
        return self.extract_key_phrases(text)[:5]

    def _get_trust_score_for_source(self, source: str) -> float:
        """Get trust score for a news source."""
        if not source:
            return 0.5
        
        source_lower = source.lower()
        
        # High trust Dutch sources - prioritized for Dutch business analysis
        tier1_dutch = ['fd.nl', 'nrc.nl']  # Tier 1: Highest trust business sources
        if any(trusted in source_lower for trusted in tier1_dutch):
            return 1.0
        
        tier2_dutch = ['nos.nl', 'volkskrant.nl', 'trouw.nl']  # Tier 2: High trust general news
        if any(trusted in source_lower for trusted in tier2_dutch):
            return 0.9
        
        tier3_dutch = ['bnr.nl', 'mt.nl', 'ad.nl', 'telegraaf.nl']  # Tier 3: Medium trust
        if any(trusted in source_lower for trusted in tier3_dutch):
            return 0.8
        
        # High trust international sources
        trusted_intl = ['reuters.com', 'bloomberg.com', 'ft.com', 'bbc.com']
        if any(trusted in source_lower for trusted in trusted_intl):
            return 1.0
        
        # Medium trust sources
        if 'news' in source_lower or 'dagblad' in source_lower:
            return 0.7
        
        return 0.5

    async def _generate_overall_analysis(
        self, company_name: str, articles: List[NewsArticle]
    ) -> NewsAnalysis:
        """Generate overall news analysis from individual articles."""
        if not articles:
            empty_positive = PositiveNews(count=0, average_sentiment=0.0, articles=[])
            empty_negative = NegativeNews(count=0, average_sentiment=0.0, articles=[])
            
            return NewsAnalysis(
                positive_news=empty_positive,
                negative_news=empty_negative,
                overall_sentiment=0.0,
                sentiment_summary={"positive": 0, "neutral": 0, "negative": 0},
                total_relevance=0.0,
                total_articles_found=0,
                articles=[],
                key_topics=[],
                risk_indicators=[],
                summary=f"No relevant news articles found for {company_name}."
            )
        
        # Remove duplicates based on URL before categorizing
        seen_urls = set()
        unique_articles = []
        for article in articles:
            if article.url and article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)
            elif not article.url:
                unique_articles.append(article)  # Keep articles without URL
        
        logger.info(f"Deduplicated articles: {len(articles)} -> {len(unique_articles)} (removed {len(articles) - len(unique_articles)} duplicates)")
        
        # Separate positive and negative articles from deduplicated list
        positive_articles = [a for a in unique_articles if a.sentiment_score > 0.1]
        negative_articles = [a for a in unique_articles if a.sentiment_score < -0.1]
        
        # Calculate sentiment averages from deduplicated articles
        overall_sentiment = sum(a.sentiment_score for a in unique_articles) / len(unique_articles)
        
        positive_avg_sentiment = (
            sum(a.sentiment_score for a in positive_articles) / len(positive_articles)
            if positive_articles else 0.0
        )
        negative_avg_sentiment = (
            sum(a.sentiment_score for a in negative_articles) / len(negative_articles)
            if negative_articles else 0.0
        )
        
        # Calculate total relevance from deduplicated articles
        total_relevance = sum(a.relevance_score for a in unique_articles) / len(unique_articles)
        
        # Extract key topics and risk indicators from deduplicated articles
        key_topics = set()
        risk_indicators = set()
        
        for article in unique_articles:
            # Add categories as key topics
            key_topics.update(article.categories)
            
            # Extract topics from content
            title_lower = article.title.lower()
            summary_lower = article.summary.lower()
            text = title_lower + ' ' + summary_lower
            
            # Key topics
            if any(word in text for word in ['growth', 'expansion', 'success', 'award', 'groei', 'uitbreiding']):
                key_topics.add('Business Growth')
            if any(word in text for word in ['financial', 'revenue', 'profit', 'earnings', 'financieel', 'omzet', 'winst']):
                key_topics.add('Financial Performance')
            if any(word in text for word in ['innovation', 'technology', 'digital', 'innovatie', 'technologie']):
                key_topics.add('Innovation & Technology')
            
            # Risk indicators for negative articles
            if article.sentiment_score < -0.3:
                if any(word in text for word in ['lawsuit', 'legal', 'investigation', 'rechtszaak', 'juridisch', 'onderzoek']):
                    risk_indicators.add('Legal Issues')
                if any(word in text for word in ['financial', 'loss', 'debt', 'bankruptcy', 'verlies', 'schuld', 'faillissement']):
                    risk_indicators.add('Financial Concerns')
                if any(word in text for word in ['regulatory', 'compliance', 'fine', 'penalty', 'regelgeving', 'boete']):
                    risk_indicators.add('Regulatory Issues')
                if any(word in text for word in ['scandal', 'fraud', 'corruption', 'schandaal', 'fraude', 'corruptie']):
                    risk_indicators.add('Reputation Risk')
        
        # Convert sets to lists
        key_topics = list(key_topics) if key_topics else ['General Business']
        risk_indicators = list(risk_indicators)
        
        # Create positive and negative news summaries
        positive_news = PositiveNews(
            count=len(positive_articles),
            average_sentiment=positive_avg_sentiment,
            articles=positive_articles
        )
        
        negative_news = NegativeNews(
            count=len(negative_articles),
            average_sentiment=negative_avg_sentiment,
            articles=negative_articles
        )
        
        # Generate summary
        summary_parts = []
        if positive_articles:
            summary_parts.append(f"{len(positive_articles)} positive articles found")
        if negative_articles:
            summary_parts.append(f"{len(negative_articles)} negative articles found")
        
        if overall_sentiment > 0.2:
            summary_parts.append("Overall sentiment is positive")
        elif overall_sentiment < -0.2:
            summary_parts.append("Overall sentiment is negative")
        else:
            summary_parts.append("Overall sentiment is neutral")
        
        summary = f"Analysis of {len(unique_articles)} articles for {company_name}. " + '. '.join(summary_parts) + "."
        
        # Calculate sentiment summary percentages
        total_articles = len(unique_articles)
        positive_count = len(positive_articles)
        negative_count = len(negative_articles)
        neutral_count = total_articles - positive_count - negative_count
        
        sentiment_summary = {
            "positive": round((positive_count / total_articles * 100), 1) if total_articles > 0 else 0,
            "neutral": round((neutral_count / total_articles * 100), 1) if total_articles > 0 else 0,
            "negative": round((negative_count / total_articles * 100), 1) if total_articles > 0 else 0
        }
        
        return NewsAnalysis(
            positive_news=positive_news,
            negative_news=negative_news,
            overall_sentiment=overall_sentiment,
            sentiment_summary=sentiment_summary,
            total_relevance=total_relevance,
            total_articles_found=len(unique_articles),
            articles=unique_articles,  # For backward compatibility (now deduplicated)
            key_topics=key_topics,
            risk_indicators=risk_indicators,
            summary=summary
        )

    def analyze_sentiment(self, text: str) -> float:
        """Analyze sentiment of a text snippet."""
        # This is a simplified version - in practice, you might use the OpenAI API
        # For now, return a basic sentiment score
        positive_words = ['good', 'great', 'excellent', 'positive', 'success', 'growth', 'profit']
        negative_words = ['bad', 'terrible', 'negative', 'loss', 'problem', 'issue', 'decline']
        
        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count + negative_count == 0:
            return 0.0
        
        return (positive_count - negative_count) / (positive_count + negative_count)

    def classify_relevance(self, article: Dict[str, Any], company: str) -> float:
        """Classify relevance of an article to a company."""
        title = article.get('title', '').lower()
        content = article.get('content', '').lower()
        company_lower = company.lower()
        
        # Simple relevance scoring
        relevance_score = 0.0
        
        # Company name mentions
        title_mentions = title.count(company_lower)
        content_mentions = content.count(company_lower)
        
        if title_mentions > 0:
            relevance_score += 0.6
        if content_mentions > 0:
            relevance_score += 0.3
        if content_mentions > 2:
            relevance_score += 0.1
        
        return min(1.0, relevance_score)

    def extract_key_phrases(self, text: str) -> List[str]:
        """Extract key phrases from text."""
        # Simple keyword extraction
        import re
        
        # Remove common stop words and extract meaningful phrases
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must'}
        
        meaningful_words = [word for word in words if len(word) > 3 and word not in stop_words]
        
        # Count word frequency
        word_counts = {}
        for word in meaningful_words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # Return top keywords
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:10]]

    def _generate_cache_key(self, company_name: str, search_params: Dict[str, Any], contact_person: str = None) -> str:
        """Generate a cache key for the search parameters."""
        key_data = {
            'company': company_name.lower(),
            'contact_person': contact_person.lower() if contact_person else None,
            'params': sorted(search_params.items()),
            'date': datetime.now().date().isoformat()  # Include date for daily cache invalidation
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if still valid."""
        if cache_key not in self.cache:
            return None
        
        # Check TTL
        if cache_key in self.cache_ttl:
            if time.time() > self.cache_ttl[cache_key]:
                # Expired
                del self.cache[cache_key]
                del self.cache_ttl[cache_key]
                return None
        
        return self.cache[cache_key]

    def _cache_result(self, cache_key: str, result: Dict[str, Any], ttl_hours: int = 6):
        """Cache a result with TTL."""
        self.cache[cache_key] = result
        self.cache_ttl[cache_key] = time.time() + (ttl_hours * 3600)
        
        # Simple cache size management
        if len(self.cache) > 100:
            # Remove oldest entries
            oldest_keys = sorted(self.cache_ttl.keys(), key=self.cache_ttl.get)[:20]
            for key in oldest_keys:
                self.cache.pop(key, None)
                self.cache_ttl.pop(key, None)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage and cost statistics."""
        # Approximate cost calculation (these rates are examples)
        input_cost_per_token = 0.00001  # $0.01 per 1K tokens
        output_cost_per_token = 0.00003  # $0.03 per 1K tokens
        
        total_cost = (
            self.total_input_tokens * input_cost_per_token +
            self.total_output_tokens * output_cost_per_token
        )
        
        return {
            'total_requests': self.total_requests,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_tokens': self.total_input_tokens + self.total_output_tokens,
            'estimated_cost_usd': round(total_cost, 4),
            'cache_size': len(self.cache)
        }