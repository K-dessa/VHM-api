import asyncio
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus, urlparse

import httpx
import structlog
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.models.response_models import (
    NewsAnalysis,
    NewsArticle,
    NewsItem,
    PositiveNews,
    NegativeNews,
)
from app.services.google_search import GoogleSearchClient

logger = structlog.get_logger()


class RSSNewsSearch:
    """RSS-based news search using Google News RSS feeds as specified in improved workflow."""

    def __init__(self):
        self.timeout = 10
        self.user_agent = "Mozilla/5.0 (compatible; BedrijfsanalyseBot/1.0)"
        self.base_url = "https://news.google.com/rss/search"

        # Paywall sources to filter out (as per workflow specification)
        self.paywall_sources = {"nrc.nl", "fd.nl", "volkskrant.nl", "telegraaf.nl"}

        # Dutch news sources whitelist for Dutch analysis
        self.dutch_whitelist = {"nos.nl", "nu.nl", "rtlz.nl", "bnr.nl", "ad.nl"}

    async def search_news(
        self,
        company_name: str,
        max_results: int = 10,
        dutch_focus: bool = False,
        simple_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for news articles using Google News RSS feeds as per improved workflow.
        Returns list of article dictionaries with title, url, source, date, content.

        Args:
            company_name: Name of the company to search for
            max_results: Maximum number of results to return
            dutch_focus: Focus on Dutch sources and filter paywall sources
            simple_mode: Use simplified search for faster results
        """
        try:
            logger.info(
                f"Starting RSS news search for: {company_name} (dutch_focus: {dutch_focus}, simple_mode: {simple_mode})"
            )

            # Build RSS feed URL
            rss_url = await self._build_rss_url(company_name, dutch_focus)

            # Fetch RSS feed
            rss_articles = await self._fetch_rss_feed(
                rss_url, max_results if simple_mode else max_results * 2
            )

            # Filter paywall sources if needed
            if dutch_focus:
                rss_articles = self._filter_paywall_sources(rss_articles)
                # Apply Dutch whitelist if specified
                rss_articles = self._apply_dutch_whitelist(rss_articles)

            # Limit results
            rss_articles = rss_articles[:max_results]

            # Optionally crawl open articles for content (as per workflow)
            if not simple_mode and rss_articles:
                rss_articles = await self._crawl_open_articles(rss_articles)

            logger.info(f"RSS search completed: found {len(rss_articles)} articles")
            return rss_articles

        except Exception as e:
            logger.error(f"RSS news search failed: {e}")
            return []

    async def _build_rss_url(self, company_name: str, dutch_focus: bool = False) -> str:
        """
        Build Google News RSS feed URL as per workflow specification.
        Format: https://news.google.com/rss/search?q="<BEDRIJFSNAAM>"&hl=nl&gl=NL&ceid=NL:nl
        """
        # Encode company name for URL
        encoded_company = quote_plus(f'"{company_name}"')

        # Base RSS URL with Dutch locale settings
        base_url = f"{self.base_url}?q={encoded_company}&hl=nl&gl=NL&ceid=NL:nl"

        logger.info(f"Built RSS URL: {base_url}")
        return base_url

    async def _fetch_rss_feed(
        self, rss_url: str, max_items: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Fetch and parse RSS feed from Google News.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, headers={"User-Agent": self.user_agent}
            ) as client:
                response = await client.get(rss_url)

                if response.status_code != 200:
                    logger.warning(f"RSS feed fetch failed: {response.status_code}")
                    return []

                # Parse RSS XML
                root = ET.fromstring(response.text)
                articles = []

                # Find all item elements in the RSS feed
                for item in root.findall(".//item")[:max_items]:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_date_elem = item.find("pubDate")
                    description_elem = item.find("description")

                    if title_elem is not None and link_elem is not None:
                        # Extract source from link
                        source = self._extract_source_from_url(link_elem.text or "")

                        # Parse publication date
                        pub_date = self._parse_rss_date(
                            pub_date_elem.text if pub_date_elem is not None else ""
                        )

                        article = {
                            "title": title_elem.text or "",
                            "url": link_elem.text or "",
                            "source": source,
                            "date": pub_date,
                            "content": description_elem.text or ""
                            if description_elem is not None
                            else "",
                        }

                        articles.append(article)

                logger.info(f"Fetched {len(articles)} articles from RSS feed")
                return articles

        except ET.ParseError as e:
            logger.error(f"RSS XML parsing error: {e}")
            return []
        except Exception as e:
            logger.error(f"RSS feed fetch error: {e}")
            return []

    def _extract_source_from_url(self, url: str) -> str:
        """Extract source domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except:
            return "unknown"

    def _parse_rss_date(self, date_str: str) -> datetime:
        """Parse RSS date string to datetime object."""
        try:
            # RSS dates are typically in RFC 2822 format
            # Example: "Wed, 02 Oct 2002 08:00:00 EST"
            from email.utils import parsedate_to_datetime

            return parsedate_to_datetime(date_str)
        except:
            # Fallback to current time
            return datetime.now()

    def _filter_paywall_sources(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter out paywall sources as specified in the workflow:
        Remove NRC, FD, Volkskrant, Telegraaf.
        """
        filtered = []
        removed_count = 0

        for article in articles:
            source = article.get("source", "").lower()

            # Check if source is in paywall list
            is_paywall = any(paywall in source for paywall in self.paywall_sources)

            if not is_paywall:
                filtered.append(article)
            else:
                removed_count += 1
                logger.debug(f"Filtered out paywall source: {source}")

        logger.info(
            f"Paywall filtering: kept {len(filtered)}, removed {removed_count} articles"
        )
        return filtered

    def _apply_dutch_whitelist(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply Dutch news sources whitelist: NOS, NU.nl, RTL Z, BNR, AD.
        """
        whitelisted = []
        other_sources = []

        for article in articles:
            source = article.get("source", "").lower()

            # Check if source is in whitelist
            is_whitelisted = any(trusted in source for trusted in self.dutch_whitelist)

            if is_whitelisted:
                whitelisted.append(article)
            else:
                other_sources.append(article)

        # Prioritize whitelisted sources but include others if needed
        result = whitelisted + other_sources

        logger.info(
            f"Dutch whitelist: prioritized {len(whitelisted)} whitelisted, {len(other_sources)} other sources"
        )
        return result

    async def _crawl_open_articles(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Optionally crawl open articles with Crawl4AI as specified in workflow.
        This attempts to get full content from freely accessible articles.
        """
        try:
            # Import Crawl4AI here to avoid dependency issues if not installed
            from crawl4ai import AsyncWebCrawler

            enhanced_articles = []
            crawl_count = 0
            max_crawls = min(5, len(articles))  # Limit crawling for performance

            async with AsyncWebCrawler(
                headless=True, verbose=False, user_agent=self.user_agent
            ) as crawler:
                for article in articles:
                    if crawl_count >= max_crawls:
                        # Add remaining articles without crawling
                        enhanced_articles.append(article)
                        continue

                    url = article.get("url", "")
                    if not url:
                        enhanced_articles.append(article)
                        continue

                    try:
                        # Attempt to crawl the article
                        result = await crawler.arun(
                            url=url,
                            word_count_threshold=50,
                            bypass_cache=True,
                            timeout=10,
                            magic=True,
                            markdown=True,
                        )

                        if result.success and result.markdown:
                            # Update article with crawled content
                            article["content"] = result.markdown[:3000]  # Limit length
                            logger.debug(f"Successfully crawled content from: {url}")
                        else:
                            logger.debug(f"Failed to crawl content from: {url}")

                        enhanced_articles.append(article)
                        crawl_count += 1

                    except Exception as e:
                        logger.warning(f"Crawling failed for {url}: {e}")
                        enhanced_articles.append(article)

            logger.info(
                f"Content crawling: enhanced {crawl_count} out of {len(articles)} articles"
            )
            return enhanced_articles

        except ImportError:
            logger.warning("Crawl4AI not available, skipping content crawling")
            return articles
        except Exception as e:
            error_msg = str(e)
            if (
                "Executable doesn't exist" in error_msg
                or "playwright install" in error_msg.lower()
            ):
                logger.error(
                    "Playwright browser not installed. Run 'playwright install' before crawling.",
                    error=error_msg,
                )
            else:
                logger.error(f"Content crawling error: {error_msg}")
            return articles

    async def search_news_simple(
        self, company_name: str, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Simple RSS news search for the simple analysis endpoint.
        Uses max 10 items and fast fetch as specified in workflow.
        """
        return await self.search_news(
            company_name=company_name,
            max_results=max_results,
            dutch_focus=False,
            simple_mode=True,
        )

    def _extract_company_name(self, search_query: str) -> str:
        """Extract company name from search query, removing sentiment keywords."""
        # Remove common search modifiers to get clean company name
        stopwords = {
            "news",
            "positive",
            "negative",
            "success",
            "problems",
            "lawsuit",
            "scandal",
            "investigation",
            "achievements",
            "growth",
            "expansion",
            "and",
            "or",
            "(",
            ")",
            "award",
            "achievement",
            "recognition",
            "controversy",
            "fine",
            "penalty",
        }

        # Split and clean
        terms = search_query.lower().split()
        clean_terms = []

        for term in terms:
            # Remove punctuation and check against stopwords
            clean_term = term.strip("()\"'.,!")
            if clean_term not in stopwords and len(clean_term) > 2:
                clean_terms.append(clean_term)

        # Reconstruct company name
        company_name = " ".join(clean_terms)
        return company_name or "company"


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

        # Initialize RSS news search
        self.rss_search = RSSNewsSearch()
        self.cache_ttl = {}

        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0

        # Optional Google Search
        self.google_search: Optional[GoogleSearchClient] = None
        try:
            if settings.GOOGLE_SEARCH_API_KEY and settings.GOOGLE_SEARCH_ENGINE_ID:
                self.google_search = GoogleSearchClient()
                logger.info("Google Search API enabled for news enrichment")
            else:
                logger.info(
                    "Google Search API not configured; skipping web search enrichment"
                )
        except Exception as e:
            logger.warning("Failed to initialize Google Search client", error=str(e))

    async def search_dutch_company_news(
        self,
        company_name: str,
        search_params: Dict[str, Any],
        contact_person: str = None,
    ) -> NewsAnalysis:
        """
        Search and analyze Dutch news about a company using RSS feeds with Dutch focus.
        Uses Dutch news sources whitelist and filters paywall sources as per workflow.
        """
        logger.info(
            "Starting Dutch RSS news search", company=company_name, params=search_params
        )

        try:
            # Generate cache key including contact person and Dutch focus
            cache_key = self._generate_cache_key(
                f"dutch_{company_name}", search_params, contact_person
            )

            # Check cache first
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                logger.info("Returning cached Dutch result", company=company_name)
                return NewsAnalysis.model_validate(cached_result)

            # Perform Dutch-focused RSS news search
            search_results = await self._perform_dutch_rss_search(
                company_name, search_params, contact_person
            )

            # Analyze sentiment and relevance for each article in parallel
            logger.info(f"Starting parallel Dutch analysis of {len(search_results)} articles")
            
            # Create tasks for parallel processing
            analysis_tasks = []
            for article in search_results:
                task = asyncio.create_task(self._analyze_article(article, company_name))
                analysis_tasks.append(task)
            
            # Wait for all analyses to complete
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and filter out exceptions
            analyzed_articles = []
            for i, result in enumerate(analysis_results):
                if isinstance(result, Exception):
                    logger.warning(f"Dutch article analysis failed for article {i}: {result}")
                    continue
                if result:
                    analyzed_articles.append(result)
            
            logger.info(f"Parallel Dutch analysis completed: {len(analyzed_articles)} articles analyzed successfully")

            # Filter by relevance threshold (more inclusive for Dutch sources)
            relevant_articles = [
                article
                for article in analyzed_articles
                if article.relevance_score >= 0.3  # Lower threshold for Dutch sources
            ]

            # Generate overall analysis
            news_analysis = await self._generate_overall_analysis(
                company_name, relevant_articles
            )

            # Cache the result
            self._cache_result(cache_key, news_analysis.model_dump(), ttl_hours=6)

            logger.info(
                "Dutch news search completed",
                company=company_name,
                total_found=len(search_results),
                relevant=len(relevant_articles),
            )

            return news_analysis

        except Exception as e:
            logger.error(
                "Dutch news search failed",
                company=company_name,
                error=str(e),
                exc_info=True,
            )
            return self._create_empty_analysis(company_name)

    async def search_company_news_simple(
        self, company_name: str, max_results: int = 10
    ) -> NewsAnalysis:
        """
        Simple news search for the simple analysis endpoint.
        Uses RSS feeds with max 10 items for fast results as per workflow.
        """
        logger.info("Starting simple RSS news search", company=company_name)

        try:
            # Use simple RSS search (no crawling, fast fetch)
            rss_articles = await self.rss_search.search_news_simple(
                company_name=company_name, max_results=max_results
            )

            articles: List[Dict[str, Any]] = rss_articles

            # Always enrich with a small Google Custom Search if configured
            if self.google_search:
                try:
                    queries: List[str] = [f'"{company_name}"']
                    google_items: List[Dict[str, Any]] = []
                    for q in queries:
                        items = await self.google_search.search(
                            q,
                            num=10,
                            lang_nl=True,
                            site_nl_only=False,
                            news_only=False,
                        )
                        if items:
                            google_items.extend(items)

                    # Prepend Google items so they aren't truncated
                    combined = google_items + articles
                    existing_urls: Set[str] = set()
                    articles = []
                    added = 0
                    for item in combined:
                        url = item.get("url")
                        if url and url not in existing_urls:
                            articles.append(item)
                            existing_urls.add(url)
                            if item in google_items:
                                added += 1
                    logger.info(
                        "Google web enrichment merged for simple search",
                        added=added,
                        total=len(articles),
                    )
                except Exception as e:
                    logger.warning(
                        "Google web enrichment failed for simple search", error=str(e)
                    )

            # Respect max_results to keep processing bounded
            if len(articles) > max_results:
                articles = articles[:max_results]

            # Quick analysis without deep content processing - parallel processing
            logger.info(f"Starting parallel simple analysis of {len(articles)} articles")
            
            # Create tasks for parallel processing
            analysis_tasks = []
            for article in articles:
                task = asyncio.create_task(self._analyze_article(article, company_name))
                analysis_tasks.append(task)
            
            # Wait for all analyses to complete
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and filter out exceptions
            analyzed_articles = []
            for i, result in enumerate(analysis_results):
                if isinstance(result, Exception):
                    logger.warning(f"Simple article analysis failed for article {i}: {result}")
                    continue
                if (
                    result and result.relevance_score >= 0.2
                ):  # Very inclusive for simple mode
                    analyzed_articles.append(result)
            
            logger.info(f"Parallel simple analysis completed: {len(analyzed_articles)} articles analyzed successfully")

            # Generate lightweight analysis
            news_analysis = await self._generate_overall_analysis(
                company_name, analyzed_articles
            )

            logger.info(
                "Simple news search completed",
                company=company_name,
                articles_found=len(articles),
                analyzed=len(analyzed_articles),
            )

            return news_analysis

        except Exception as e:
            logger.error(
                "Simple news search failed", company=company_name, error=str(e)
            )
            return self._create_empty_analysis(company_name)

    async def search_company_news(
        self,
        company_name: str,
        search_params: Dict[str, Any],
        contact_person: str = None,
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
            cache_key = self._generate_cache_key(
                company_name, search_params, contact_person
            )

            # Check cache first
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                logger.info("Returning cached result", company=company_name)
                return NewsAnalysis.model_validate(cached_result)

            # Perform RSS news search
            search_results = await self._perform_rss_search(
                company_name, search_params, contact_person
            )

            # Analyze sentiment and relevance for each article in parallel
            logger.info(f"Starting parallel analysis of {len(search_results)} articles")
            
            # Create tasks for parallel processing
            analysis_tasks = []
            for article in search_results:
                task = asyncio.create_task(self._analyze_article(article, company_name))
                analysis_tasks.append(task)
            
            # Wait for all analyses to complete
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and filter out exceptions
            analyzed_articles = []
            for i, result in enumerate(analysis_results):
                if isinstance(result, Exception):
                    logger.warning(f"Article analysis failed for article {i}: {result}")
                    continue
                if result:
                    analyzed_articles.append(result)
            
            logger.info(f"Parallel analysis completed: {len(analyzed_articles)} articles analyzed successfully")

            # Filter by relevance threshold (lowered from 0.6 to 0.4 for more inclusive results)
            relevant_articles = [
                article
                for article in analyzed_articles
                if article.relevance_score >= 0.4
            ]

            # Backup strategy: ensure minimum articles if strict filtering removes too many
            if len(relevant_articles) < 5 and len(analyzed_articles) > 0:
                # Sort by relevance and take best articles even if below 0.4 threshold
                backup_articles = sorted(
                    analyzed_articles, key=lambda x: x.relevance_score, reverse=True
                )
                relevant_articles = backup_articles[: min(8, len(backup_articles))]

                logger.info(
                    f"Applied backup filtering: included {len(relevant_articles)} articles "
                    f"(minimum relevance: {min(a.relevance_score for a in relevant_articles):.2f})"
                )

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
                relevant=len(relevant_articles),
            )

            return news_analysis

        except Exception as e:
            logger.error(
                "News search failed", company=company_name, error=str(e), exc_info=True
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
                summary="News analysis failed due to technical issues.",
            )

    async def _perform_rss_search(
        self,
        company_name: str,
        search_params: Dict[str, Any],
        contact_person: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform RSS-based news search for standard analysis.
        Uses RSS feeds without Dutch focus filtering.
        """
        try:
            logger.info(f"Starting RSS search for: {company_name}")

            # Get articles using RSS (no Dutch focus for standard analysis)
            articles = await self.rss_search.search_news(
                company_name=company_name,
                max_results=20,  # Get more for filtering
                dutch_focus=False,  # No Dutch filtering for standard analysis
                simple_mode=False,  # Allow content crawling
            )

            # Additional search with contact person if provided
            if contact_person:
                logger.info(f"Adding contact person search: {contact_person}")

                # Extract first and last name for flexible searching
                names = contact_person.strip().split()
                if len(names) >= 2:
                    contact_query = f"{company_name} {names[0]} {names[-1]}"
                else:
                    contact_query = f"{company_name} {contact_person}"

                contact_articles = await self.rss_search.search_news(
                    company_name=contact_query,
                    max_results=10,
                    dutch_focus=False,
                    simple_mode=False,
                )

                # Merge results, avoiding duplicates
                existing_urls = {
                    article.get("url") for article in articles if article.get("url")
                }
                for article in contact_articles:
                    if article.get("url") not in existing_urls:
                        articles.append(article)

            # Always enrich with Google Custom Search results when configured
            if self.google_search:
                try:
                    # Build a small set of focused queries
                    queries: List[str] = [f'"{company_name}"']
                    if contact_person:
                        queries.append(f'"{company_name}" "{contact_person}"')

                    # Execute searches (cap to keep latency low)
                    google_items: List[Dict[str, Any]] = []
                    for q in queries[:2]:
                        items = await self.google_search.search(
                            q,
                            num=10,
                            lang_nl=True,
                            site_nl_only=False,
                            news_only=False,
                        )
                        if items:
                            google_items.extend(items)

                    # Deduplicate and merge
                    existing_urls = {a.get("url") for a in articles if a.get("url")}
                    added = 0
                    for item in google_items:
                        url = item.get("url")
                        if url and url not in existing_urls:
                            articles.append(item)
                            existing_urls.add(url)
                            added += 1
                    logger.info(
                        "Google web enrichment merged for standard search",
                        added=added,
                        total=len(articles),
                    )
                except Exception as e:
                    logger.warning(
                        "Google web enrichment failed for standard search",
                        error=str(e),
                    )

            logger.info(f"RSS search completed: found {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"RSS search failed: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def _perform_web_search(
        self,
        company_name: str,
        search_params: Dict[str, Any],
        contact_person: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform actual web search using OpenAI function calling.
        Searches for both positive and negative news about the company.
        """
        date_range = search_params.get("date_range", "6m")
        include_positive = search_params.get("include_positive", True)
        include_negative = search_params.get("include_negative", True)

        # Use RSS as primary news source
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
                f"{base_query} positive news success achievements growth expansion",
                "positive",
                date_range,
            )
            search_results.extend(positive_results)

            # Additional search with contact person if provided
            if contact_person:
                contact_positive_results = await self._search_web_content(
                    f"{contact_query} success achievement award recognition",
                    "positive",
                    date_range,
                )
                search_results.extend(contact_positive_results)

        # Search for negative news
        if include_negative:
            negative_results = await self._search_web_content(
                f"{base_query} negative news problems lawsuit scandal investigation",
                "negative",
                date_range,
            )
            search_results.extend(negative_results)

            # Additional search with contact person if provided
            if contact_person:
                contact_negative_results = await self._search_web_content(
                    f"{contact_query} lawsuit scandal investigation controversy",
                    "negative",
                    date_range,
                )
                search_results.extend(contact_negative_results)

        # Enrich with Google Custom Search results (general web) if available
        if self.google_search:
            try:
                # Base query with exact company name
                queries = [f'"{company_name}"']
                if contact_person:
                    queries.append(f'"{company_name}" "{contact_person}"')

                # Sentiment hints improve diversity of pages discovered
                if include_positive:
                    queries.append(f'"{company_name}" award OR contract OR partnership')
                if include_negative:
                    queries.append(f'"{company_name}" lawsuit OR investigation OR fine')

                google_items: List[Dict[str, Any]] = []
                # Limit number of calls to keep performance reasonable
                for q in queries[:3]:
                    items = await self.google_search.search(
                        q,
                        num=10,
                        lang_nl=True,
                        site_nl_only=False,
                        news_only=False,
                    )
                    if items:
                        google_items.extend(items)

                # Deduplicate by URL and merge
                existing_urls = {
                    item.get("url") for item in search_results if item.get("url")
                }
                for item in google_items:
                    url = item.get("url")
                    if url and url not in existing_urls:
                        search_results.append(item)
                        existing_urls.add(url)

                logger.info("Merged Google web results", total=len(search_results))
            except Exception as e:
                logger.warning("Google web enrichment failed", error=str(e))

        return search_results

    async def _perform_dutch_rss_search(
        self,
        company_name: str,
        search_params: Dict[str, Any],
        contact_person: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform Dutch-focused RSS search using Google News RSS feeds.
        Applies Dutch whitelist and filters paywall sources as per workflow.
        """
        try:
            logger.info(f"Starting Dutch RSS search for: {company_name}")

            # Get articles using RSS with Dutch focus
            articles = await self.rss_search.search_news(
                company_name=company_name,
                max_results=20,  # Get more for filtering
                dutch_focus=True,  # Enable Dutch filtering and whitelist
                simple_mode=False,  # Allow content crawling
            )

            # Additional search with contact person if provided
            if contact_person:
                logger.info(f"Adding contact person search: {contact_person}")

                # Extract first and last name for flexible searching
                names = contact_person.strip().split()
                if len(names) >= 2:
                    contact_query = f"{company_name} {names[0]} {names[-1]}"
                else:
                    contact_query = f"{company_name} {contact_person}"

                contact_articles = await self.rss_search.search_news(
                    company_name=contact_query,
                    max_results=10,
                    dutch_focus=True,
                    simple_mode=False,
                )

                # Merge results, avoiding duplicates
                existing_urls = {
                    article.get("url") for article in articles if article.get("url")
                }
                for article in contact_articles:
                    if article.get("url") not in existing_urls:
                        articles.append(article)

            # Enrich with Google Custom Search focused on NL domains if available
            if self.google_search:
                try:
                    queries = [f'"{company_name}"']
                    if contact_person:
                        queries.append(f'"{company_name}" "{contact_person}"')

                    google_items: List[Dict[str, Any]] = []
                    for q in queries:
                        items = await self.google_search.search(
                            q,
                            num=10,
                            lang_nl=True,
                            site_nl_only=True,
                            news_only=False,
                        )
                        if items:
                            google_items.extend(items)

                    existing_urls = {a.get("url") for a in articles if a.get("url")}
                    added = 0
                    for item in google_items:
                        url = item.get("url")
                        if url and url not in existing_urls:
                            articles.append(item)
                            existing_urls.add(url)
                            added += 1
                    logger.info(
                        "Dutch Google web enrichment merged",
                        added=added,
                        total=len(articles),
                    )
                except Exception as e:
                    logger.warning("Dutch Google web enrichment failed", error=str(e))

            logger.info(
                f"Dutch RSS search completed: found {len(articles)} articles (with enrichment)"
            )
            return articles

        except Exception as e:
            logger.error(f"Dutch RSS search failed: {e}")
            return []

    def _create_empty_analysis(self, company_name: str) -> NewsAnalysis:
        """Create empty analysis for error cases."""
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
            summary=f"News analysis failed for {company_name} due to technical issues.",
        )

    def _generate_search_queries(
        self,
        company_name: str,
        date_range: str,
        include_positive: bool,
        include_negative: bool,
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
        Use RSS news search to find actual news articles about the company.
        """
        try:
            logger.info(f"Searching RSS content for: {search_query}")

            # Extract company name from search query
            company_name = self._extract_company_name(search_query)

            # Use RSS search to get articles
            articles = await self.rss_search.search_news(company_name, max_results=10)

            # Convert date strings to datetime objects if needed
            for article in articles:
                if "date" in article and isinstance(article["date"], str):
                    try:
                        article["date"] = datetime.strptime(article["date"], "%Y-%m-%d")
                    except ValueError:
                        article["date"] = datetime.now()
                elif "date" not in article:
                    article["date"] = datetime.now()

            logger.info(f"Found {len(articles)} articles for query: {search_query}")
            return articles

        except Exception as e:
            logger.error(f"Web search failed for query: {search_query}, error: {e}")
            return []

    @retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5)
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
                    {"role": "user", "content": user_prompt},
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
                start_idx = content.find("{")
                end_idx = content.rfind("}") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx]
                    analysis = json.loads(json_str)
                else:
                    # Fallback parsing
                    analysis = self._parse_analysis_fallback(content)
            except json.JSONDecodeError:
                analysis = self._parse_analysis_fallback(content)

            # Validate and create NewsItem
            sentiment_score = max(
                -1.0, min(1.0, float(analysis.get("sentiment_score", 0.0)))
            )
            relevance_score = max(
                0.0, min(1.0, float(analysis.get("relevance_score", 0.0)))
            )
            summary = str(analysis.get("summary", article.get("title", "")))[:200]
            classification = analysis.get("classification", "neutraal nieuws")

            # Log the OpenAI analysis for transparency
            logger.info(
                f"OpenAI Analysis - {company_name}: {classification} (sentiment: {sentiment_score}, relevance: {relevance_score})"
            )
            logger.info(f"Summary: {summary}")
            logger.info(f"URL: {article.get('url', '')}")

            return NewsArticle(
                title=article.get("title", ""),
                source=article.get("source", "Unknown"),
                date=article.get("date", datetime.now()),
                summary=summary,
                sentiment_score=sentiment_score,
                relevance_score=relevance_score,
                url=article.get("url"),
                categories=self._classify_categories(
                    article.get("title", "") + " " + summary
                ),
                key_phrases=self._extract_key_phrases_ai(summary),
                trust_score=self._get_trust_score_for_source(article.get("source", "")),
            )

        except Exception as e:
            logger.warning(
                "Article analysis failed",
                article_title=article.get("title"),
                error=str(e),
            )
            return None

    def _parse_analysis_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parser for when JSON parsing fails."""
        analysis = {
            "sentiment_score": 0.0,
            "relevance_score": 0.5,
            "summary": content[:200] if content else "Analysis unavailable",
        }

        # Try to extract sentiment and relevance from text
        import re

        sentiment_match = re.search(r"sentiment[:\s]*(-?[0-9.]+)", content.lower())
        if sentiment_match:
            try:
                analysis["sentiment_score"] = float(sentiment_match.group(1))
            except ValueError:
                pass

        relevance_match = re.search(r"relevance[:\s]*([0-9.]+)", content.lower())
        if relevance_match:
            try:
                analysis["relevance_score"] = float(relevance_match.group(1))
            except ValueError:
                pass

        return analysis

    def _classify_categories(self, text: str) -> List[str]:
        """Classify article into business categories."""
        categories = []
        text_lower = text.lower()

        # Financial category
        financial_keywords = [
            "financial",
            "revenue",
            "profit",
            "loss",
            "earnings",
            "quarterly",
            "winst",
            "omzet",
            "financieel",
        ]
        if any(keyword in text_lower for keyword in financial_keywords):
            categories.append("financial")

        # Legal category
        legal_keywords = [
            "lawsuit",
            "court",
            "legal",
            "investigation",
            "rechtszaak",
            "juridisch",
            "onderzoek",
        ]
        if any(keyword in text_lower for keyword in legal_keywords):
            categories.append("legal")

        # Operational category
        operational_keywords = [
            "operations",
            "business",
            "expansion",
            "growth",
            "development",
            "bedrijfsvoering",
            "operaties",
        ]
        if any(keyword in text_lower for keyword in operational_keywords):
            categories.append("operational")

        # Regulatory category
        regulatory_keywords = [
            "regulatory",
            "compliance",
            "fine",
            "penalty",
            "regelgeving",
            "boete",
        ]
        if any(keyword in text_lower for keyword in regulatory_keywords):
            categories.append("regulatory")

        # Innovation category
        innovation_keywords = [
            "innovation",
            "technology",
            "digital",
            "tech",
            "innovatie",
            "technologie",
        ]
        if any(keyword in text_lower for keyword in innovation_keywords):
            categories.append("innovation")

        return categories if categories else ["general"]

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
        tier1_dutch = ["fd.nl", "nrc.nl"]  # Tier 1: Highest trust business sources
        if any(trusted in source_lower for trusted in tier1_dutch):
            return 1.0

        tier2_dutch = [
            "nos.nl",
            "volkskrant.nl",
            "trouw.nl",
        ]  # Tier 2: High trust general news
        if any(trusted in source_lower for trusted in tier2_dutch):
            return 0.9

        tier3_dutch = [
            "bnr.nl",
            "mt.nl",
            "ad.nl",
            "telegraaf.nl",
        ]  # Tier 3: Medium trust
        if any(trusted in source_lower for trusted in tier3_dutch):
            return 0.8

        # High trust international sources
        trusted_intl = ["reuters.com", "bloomberg.com", "ft.com", "bbc.com"]
        if any(trusted in source_lower for trusted in trusted_intl):
            return 1.0

        # Medium trust sources
        if "news" in source_lower or "dagblad" in source_lower:
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
                summary=f"No relevant news articles found for {company_name}.",
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

        logger.info(
            f"Deduplicated articles: {len(articles)} -> {len(unique_articles)} (removed {len(articles) - len(unique_articles)} duplicates)"
        )

        # Separate positive and negative articles from deduplicated list
        positive_articles = [a for a in unique_articles if a.sentiment_score > 0.1]
        negative_articles = [a for a in unique_articles if a.sentiment_score < -0.1]

        # Calculate sentiment averages from deduplicated articles
        overall_sentiment = sum(a.sentiment_score for a in unique_articles) / len(
            unique_articles
        )

        positive_avg_sentiment = (
            sum(a.sentiment_score for a in positive_articles) / len(positive_articles)
            if positive_articles
            else 0.0
        )
        negative_avg_sentiment = (
            sum(a.sentiment_score for a in negative_articles) / len(negative_articles)
            if negative_articles
            else 0.0
        )

        # Calculate total relevance from deduplicated articles
        total_relevance = sum(a.relevance_score for a in unique_articles) / len(
            unique_articles
        )

        # Extract key topics and risk indicators from deduplicated articles
        key_topics = set()
        risk_indicators = set()

        for article in unique_articles:
            # Add categories as key topics
            key_topics.update(article.categories)

            # Extract topics from content
            title_lower = article.title.lower()
            summary_lower = article.summary.lower()
            text = title_lower + " " + summary_lower

            # Key topics
            if any(
                word in text
                for word in [
                    "growth",
                    "expansion",
                    "success",
                    "award",
                    "groei",
                    "uitbreiding",
                ]
            ):
                key_topics.add("Business Growth")
            if any(
                word in text
                for word in [
                    "financial",
                    "revenue",
                    "profit",
                    "earnings",
                    "financieel",
                    "omzet",
                    "winst",
                ]
            ):
                key_topics.add("Financial Performance")
            if any(
                word in text
                for word in [
                    "innovation",
                    "technology",
                    "digital",
                    "innovatie",
                    "technologie",
                ]
            ):
                key_topics.add("Innovation & Technology")

            # Risk indicators for negative articles
            if article.sentiment_score < -0.3:
                if any(
                    word in text
                    for word in [
                        "lawsuit",
                        "legal",
                        "investigation",
                        "rechtszaak",
                        "juridisch",
                        "onderzoek",
                    ]
                ):
                    risk_indicators.add("Legal Issues")
                if any(
                    word in text
                    for word in [
                        "financial",
                        "loss",
                        "debt",
                        "bankruptcy",
                        "verlies",
                        "schuld",
                        "faillissement",
                    ]
                ):
                    risk_indicators.add("Financial Concerns")
                if any(
                    word in text
                    for word in [
                        "regulatory",
                        "compliance",
                        "fine",
                        "penalty",
                        "regelgeving",
                        "boete",
                    ]
                ):
                    risk_indicators.add("Regulatory Issues")
                if any(
                    word in text
                    for word in [
                        "scandal",
                        "fraud",
                        "corruption",
                        "schandaal",
                        "fraude",
                        "corruptie",
                    ]
                ):
                    risk_indicators.add("Reputation Risk")

        # Convert sets to lists
        key_topics = list(key_topics) if key_topics else ["General Business"]
        risk_indicators = list(risk_indicators)

        # Create positive and negative news summaries
        positive_news = PositiveNews(
            count=len(positive_articles),
            average_sentiment=positive_avg_sentiment,
            articles=positive_articles,
        )

        negative_news = NegativeNews(
            count=len(negative_articles),
            average_sentiment=negative_avg_sentiment,
            articles=negative_articles,
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

        summary = (
            f"Analysis of {len(unique_articles)} articles for {company_name}. "
            + ". ".join(summary_parts)
            + "."
        )

        # Calculate sentiment summary percentages
        total_articles = len(unique_articles)
        positive_count = len(positive_articles)
        negative_count = len(negative_articles)
        neutral_count = total_articles - positive_count - negative_count

        sentiment_summary = {
            "positive": round((positive_count / total_articles * 100), 1)
            if total_articles > 0
            else 0,
            "neutral": round((neutral_count / total_articles * 100), 1)
            if total_articles > 0
            else 0,
            "negative": round((negative_count / total_articles * 100), 1)
            if total_articles > 0
            else 0,
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
            summary=summary,
        )

    def analyze_sentiment(self, text: str) -> float:
        """Analyze sentiment of a text snippet."""
        # This is a simplified version - in practice, you might use the OpenAI API
        # For now, return a basic sentiment score
        positive_words = [
            "good",
            "great",
            "excellent",
            "positive",
            "success",
            "growth",
            "profit",
        ]
        negative_words = [
            "bad",
            "terrible",
            "negative",
            "loss",
            "problem",
            "issue",
            "decline",
        ]

        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count + negative_count == 0:
            return 0.0

        return (positive_count - negative_count) / (positive_count + negative_count)

    def classify_relevance(self, article: Dict[str, Any], company: str) -> float:
        """Classify relevance of an article to a company."""
        title = article.get("title", "").lower()
        content = article.get("content", "").lower()
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
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "should",
            "could",
            "can",
            "may",
            "might",
            "must",
        }

        meaningful_words = [
            word for word in words if len(word) > 3 and word not in stop_words
        ]

        # Count word frequency
        word_counts = {}
        for word in meaningful_words:
            word_counts[word] = word_counts.get(word, 0) + 1

        # Return top keywords
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:10]]

    def _generate_cache_key(
        self,
        company_name: str,
        search_params: Dict[str, Any],
        contact_person: str = None,
    ) -> str:
        """Generate a cache key for the search parameters."""
        key_data = {
            "company": company_name.lower(),
            "contact_person": contact_person.lower() if contact_person else None,
            "params": sorted(search_params.items()),
            "date": datetime.now()
            .date()
            .isoformat(),  # Include date for daily cache invalidation
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
            self.total_input_tokens * input_cost_per_token
            + self.total_output_tokens * output_cost_per_token
        )

        return {
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost_usd": round(total_cost, 4),
            "cache_size": len(self.cache),
        }
