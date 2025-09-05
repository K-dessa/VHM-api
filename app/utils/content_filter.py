"""Content filtering and quality control utilities for news analysis."""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


class ContentFilter:
    """Content filtering and quality control for news articles."""
    
    def __init__(self):
        """Initialize content filter with trusted sources and quality thresholds."""
        # Dutch trusted news sources
        self.trusted_dutch_sources = {
            'nos.nl', 'nu.nl', 'rtlnieuws.nl', 'telegraaf.nl', 'ad.nl',
            'fd.nl', 'parool.nl', 'volkskrant.nl', 'trouw.nl', 'nrc.nl',
            'bnr.nl', 'bndestem.nl', 'gelderlander.nl', 'tubantia.nl',
            'eindhovens.nl', 'omroepwest.nl', 'omroepbrabant.nl'
        }
        
        # International trusted news sources
        self.trusted_international_sources = {
            'reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com',
            'cnn.com', 'bbc.com', 'bbc.co.uk', 'theguardian.com',
            'techcrunch.com', 'forbes.com', 'reuters.com',
            'ap.org', 'afp.com', 'dpa.com'
        }
        
        # Combined trusted sources
        self.trusted_sources = self.trusted_dutch_sources.union(
            self.trusted_international_sources
        )
        
        # Sources to exclude (spam, low quality, etc.)
        self.excluded_sources = {
            'clickbait.com', 'spam-news.com', 'fake-news.net',
            'ad-heavy-site.com', 'content-farm.com', 'listicle-site.com',
            'facebook.com', 'twitter.com', 'instagram.com', 'tiktok.com',
            'reddit.com', 'youtube.com', 'pinterest.com'
        }
        
        # Quality thresholds
        self.min_relevance_score = 0.6
        self.min_article_length = 100  # characters
        self.max_articles_per_source = 3
        self.min_trust_score = 0.3
        
        # Language detection words
        self.dutch_indicators = {
            'de', 'het', 'een', 'van', 'en', 'in', 'op', 'voor', 'met', 'door',
            'bij', 'naar', 'over', 'onder', 'tussen', 'sinds', 'tijdens',
            'bedrijf', 'onderneming', 'maatschappij', 'organisatie'
        }
        
        self.english_indicators = {
            'the', 'and', 'of', 'in', 'to', 'for', 'with', 'on', 'by', 'from',
            'at', 'about', 'under', 'between', 'since', 'during',
            'company', 'business', 'organization', 'corporation'
        }

    def filter_articles(
        self,
        articles: List[Dict[str, Any]],
        company_name: str,
        search_params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter articles based on quality, relevance, and source criteria.
        
        Args:
            articles: List of article dictionaries
            company_name: Company name for relevance checking
            search_params: Additional search parameters
            
        Returns:
            Filtered list of high-quality, relevant articles
        """
        if not articles:
            return []
        
        search_params = search_params or {}
        
        logger.info(
            "Starting content filtering",
            total_articles=len(articles),
            company=company_name
        )
        
        filtered_articles = []
        source_counts = {}
        
        for article in articles:
            # Apply quality filters
            if not self._passes_quality_check(article):
                continue
            
            # Apply source quality filter
            if not self._passes_source_check(article):
                continue
            
            # Apply relevance filter
            relevance_score = self._calculate_relevance(article, company_name)
            if relevance_score < self.min_relevance_score:
                continue
            
            # Apply language filter
            if not self._passes_language_check(article, search_params):
                continue
            
            # Apply date filter
            if not self._passes_date_check(article, search_params):
                continue
            
            # Apply source diversity limit
            source = self._extract_domain(article.get('url', ''))
            source_count = source_counts.get(source, 0)
            if source_count >= self.max_articles_per_source:
                continue
            
            # Article passes all filters
            article['relevance_score'] = relevance_score
            article['trust_score'] = self._get_source_trust_score(source)
            article['quality_score'] = self._calculate_quality_score(article)
            
            filtered_articles.append(article)
            source_counts[source] = source_count + 1
        
        # Sort by combined score (relevance + trust + quality)
        filtered_articles.sort(
            key=lambda x: (
                x.get('relevance_score', 0) * 0.4 +
                x.get('trust_score', 0) * 0.3 +
                x.get('quality_score', 0) * 0.3
            ),
            reverse=True
        )
        
        logger.info(
            "Content filtering completed",
            original_count=len(articles),
            filtered_count=len(filtered_articles),
            company=company_name
        )
        
        return filtered_articles

    def _passes_quality_check(self, article: Dict[str, Any]) -> bool:
        """Check if article meets basic quality criteria."""
        title = article.get('title', '')
        content = article.get('content', '') or article.get('snippet', '')
        
        # Check minimum content length
        if len(content) < self.min_article_length:
            return False
        
        # Check for required fields
        if not title or not content:
            return False
        
        # Check for spam indicators
        if self._contains_spam_indicators(title + ' ' + content):
            return False
        
        # Check for duplicate content patterns
        if self._is_duplicate_content(content):
            return False
        
        return True

    def _passes_source_check(self, article: Dict[str, Any]) -> bool:
        """Check if article source meets quality criteria."""
        url = article.get('url', '')
        source = article.get('source', '')
        
        if not url and not source:
            return False
        
        domain = self._extract_domain(url) if url else source.lower()
        
        # Exclude blacklisted sources
        if any(excluded in domain for excluded in self.excluded_sources):
            return False
        
        # Check trust score
        trust_score = self._get_source_trust_score(domain)
        return trust_score >= self.min_trust_score

    def _calculate_relevance(
        self, article: Dict[str, Any], company_name: str
    ) -> float:
        """Calculate relevance score for article to company."""
        if not company_name:
            return 0.0
        
        title = article.get('title', '').lower()
        content = (article.get('content', '') or article.get('snippet', '')).lower()
        company_lower = company_name.lower()
        
        relevance_score = 0.0
        
        # Direct company name mentions
        title_mentions = title.count(company_lower)
        content_mentions = content.count(company_lower)
        
        # Title mentions are more important
        if title_mentions > 0:
            relevance_score += 0.4 + (title_mentions - 1) * 0.1
        
        # Content mentions
        if content_mentions > 0:
            relevance_score += 0.3 + min(content_mentions - 1, 3) * 0.05
        
        # Company name variations (abbreviations, etc.)
        company_variations = self._generate_company_variations(company_name)
        for variation in company_variations:
            variation_lower = variation.lower()
            if variation_lower in title:
                relevance_score += 0.2
            if variation_lower in content:
                relevance_score += 0.1
        
        # Business context keywords
        business_keywords = [
            'bedrijf', 'onderneming', 'maatschappij', 'bv', 'nv',
            'company', 'corporation', 'business', 'firm', 'ltd', 'inc'
        ]
        
        keyword_mentions = sum(
            1 for keyword in business_keywords
            if keyword in title or keyword in content
        )
        
        if keyword_mentions > 0:
            relevance_score += min(keyword_mentions * 0.05, 0.15)
        
        return min(1.0, relevance_score)

    def _passes_language_check(
        self, article: Dict[str, Any], search_params: Dict[str, Any]
    ) -> bool:
        """Check if article language matches search preferences."""
        preferred_language = search_params.get('language', 'nl')
        
        title = article.get('title', '')
        content = article.get('content', '') or article.get('snippet', '')
        text = (title + ' ' + content).lower()
        
        detected_language = self._detect_language(text)
        
        # If preferred language is specified, filter accordingly
        if preferred_language == 'nl':
            return detected_language in ['nl', 'unknown']
        elif preferred_language == 'en':
            return detected_language in ['en', 'unknown']
        
        # Accept all languages if no preference
        return True

    def _passes_date_check(
        self, article: Dict[str, Any], search_params: Dict[str, Any]
    ) -> bool:
        """Check if article date falls within search range."""
        date_range = search_params.get('date_range', '6m')
        article_date = article.get('date')
        
        if not article_date:
            return True  # Accept articles without dates
        
        if isinstance(article_date, str):
            try:
                article_date = datetime.fromisoformat(article_date.replace('Z', '+00:00'))
            except ValueError:
                return True  # Accept if we can't parse the date
        
        # Calculate date range
        end_date = datetime.now()
        if date_range == '1m':
            start_date = end_date - timedelta(days=30)
        elif date_range == '3m':
            start_date = end_date - timedelta(days=90)
        elif date_range == '6m':
            start_date = end_date - timedelta(days=180)
        else:  # 1y
            start_date = end_date - timedelta(days=365)
        
        # Make article_date timezone-naive for comparison
        if hasattr(article_date, 'tzinfo') and article_date.tzinfo:
            article_date = article_date.replace(tzinfo=None)
        
        return start_date <= article_date <= end_date

    def _contains_spam_indicators(self, text: str) -> bool:
        """Check for spam indicators in text."""
        text_lower = text.lower()
        
        spam_patterns = [
            r'click\s+here',
            r'free\s+money',
            r'urgent\s+offer',
            r'act\s+now',
            r'limited\s+time',
            r'\d+\s*clicks',
            r'you\s+won',
            r'congratulations',
            r'winner',
            r'lottery',
        ]
        
        return any(re.search(pattern, text_lower) for pattern in spam_patterns)

    def _is_duplicate_content(self, content: str) -> bool:
        """Check for duplicate or template content."""
        # Simple check for very repetitive content
        words = content.lower().split()
        if len(words) < 10:
            return False
        
        word_count = {}
        for word in words:
            word_count[word] = word_count.get(word, 0) + 1
        
        # If any word appears more than 20% of the time, it might be spam
        max_word_freq = max(word_count.values())
        return max_word_freq / len(words) > 0.2

    def _generate_company_variations(self, company_name: str) -> List[str]:
        """Generate variations of company name for matching."""
        variations = []
        
        # Remove common legal suffixes
        name_clean = re.sub(
            r'\s+(b\.?v\.?|n\.?v\.?|ltd\.?|inc\.?|corp\.?|llc\.?|sa\.?|gmbh\.?)$',
            '', company_name, flags=re.IGNORECASE
        )
        
        if name_clean != company_name:
            variations.append(name_clean)
        
        # Add abbreviation if company name has multiple words
        words = name_clean.split()
        if len(words) > 1:
            abbreviation = ''.join(word[0].upper() for word in words if len(word) > 2)
            if len(abbreviation) >= 2:
                variations.append(abbreviation)
        
        return variations

    def _detect_language(self, text: str) -> str:
        """Simple language detection."""
        words = set(text.lower().split())
        
        dutch_matches = len(words.intersection(self.dutch_indicators))
        english_matches = len(words.intersection(self.english_indicators))
        
        if dutch_matches > english_matches and dutch_matches > 0:
            return 'nl'
        elif english_matches > dutch_matches and english_matches > 0:
            return 'en'
        else:
            return 'unknown'

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return ''
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            return domain
        except Exception:
            return ''

    def _get_source_trust_score(self, domain: str) -> float:
        """Get trust score for source domain."""
        if not domain:
            return 0.0
        
        domain_lower = domain.lower()
        
        # High trust sources
        if any(trusted in domain_lower for trusted in self.trusted_sources):
            return 1.0
        
        # Medium trust - other news sites with common news TLDs
        news_indicators = ['.news', 'news.', 'nieuwsblad', 'dagblad', 'krant', 'journal']
        if any(indicator in domain_lower for indicator in news_indicators):
            return 0.7
        
        # Lower trust - other domains
        return 0.5

    def _calculate_quality_score(self, article: Dict[str, Any]) -> float:
        """Calculate quality score for article."""
        score = 0.0
        
        title = article.get('title', '')
        content = article.get('content', '') or article.get('snippet', '')
        
        # Title quality
        if len(title) > 10:
            score += 0.2
        if len(title) < 100:  # Not too long
            score += 0.1
        
        # Content quality
        if len(content) > 200:
            score += 0.2
        if len(content) > 500:
            score += 0.1
        
        # Structure indicators
        if '.' in content:  # Has sentences
            score += 0.1
        if any(char.isupper() for char in content):  # Has proper capitalization
            score += 0.1
        
        # URL quality
        url = article.get('url', '')
        if url and not any(spam in url.lower() for spam in ['spam', 'ad', 'click']):
            score += 0.2
        
        return min(1.0, score)

    def get_filter_stats(self) -> Dict[str, Any]:
        """Get filter configuration and statistics."""
        return {
            'trusted_sources_count': len(self.trusted_sources),
            'excluded_sources_count': len(self.excluded_sources),
            'min_relevance_score': self.min_relevance_score,
            'min_article_length': self.min_article_length,
            'max_articles_per_source': self.max_articles_per_source,
            'min_trust_score': self.min_trust_score,
            'dutch_sources': list(self.trusted_dutch_sources)[:10],  # Sample
            'international_sources': list(self.trusted_international_sources)[:10]  # Sample
        }