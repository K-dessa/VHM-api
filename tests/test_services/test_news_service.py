"""Tests for the news service."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from app.models.response_models import NewsAnalysis, NewsArticle, PositiveNews, NegativeNews
from app.services.news_service import NewsService


class TestNewsService:
    """Test cases for NewsService."""

    @pytest.fixture
    def mock_openai_response(self):
        """Mock OpenAI API response."""
        return ChatCompletion(
            id="test-id",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    message=ChatCompletionMessage(
                        content='{"sentiment_score": 0.7, "relevance_score": 0.8, "summary": "Positive business news"}',
                        role="assistant"
                    )
                )
            ],
            created=1234567890,
            model="gpt-4.1",
            object="chat.completion",
            usage=CompletionUsage(
                completion_tokens=50,
                prompt_tokens=100,
                total_tokens=150
            )
        )

    @pytest.fixture
    def sample_articles(self):
        """Sample articles for testing."""
        return [
            {
                'title': 'Test Company B.V. reports strong quarterly results',
                'source': 'fd.nl',
                'date': datetime.now() - timedelta(days=15),
                'url': 'https://fd.nl/test-article-1',
                'content': 'Test Company B.V. announced strong financial performance with revenue growth of 12% year-over-year.',
            },
            {
                'title': 'Test Company faces regulatory inquiry',
                'source': 'nos.nl',
                'date': datetime.now() - timedelta(days=30),
                'url': 'https://nos.nl/test-article-2',
                'content': 'Regulatory authorities have initiated an inquiry into Test Company business practices.',
            }
        ]

    @pytest.fixture
    def news_service(self):
        """Create a NewsService instance with mocked OpenAI."""
        with patch('app.services.news_service.OpenAI'):
            service = NewsService()
            service.client = MagicMock()
            return service

    def test_init_without_api_key(self):
        """Test NewsService initialization without API key."""
        with patch('app.services.news_service.settings') as mock_settings:
            mock_settings.OPENAI_API_KEY = None
            with pytest.raises(ValueError, match="OPENAI_API_KEY environment variable is required"):
                NewsService()

    def test_init_with_api_key(self):
        """Test NewsService initialization with API key."""
        with patch('app.services.news_service.settings') as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            mock_settings.OPENAI_TIMEOUT = 30
            
            with patch('app.services.news_service.OpenAI') as mock_openai:
                service = NewsService()
                assert service.model == "gpt-4.1"
                assert service.temperature == 0.1
                assert service.max_tokens == 4000
                mock_openai.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_company_news_empty_result(self, news_service):
        """Test news search with no results."""
        with patch.object(news_service, '_perform_web_search', return_value=[]):
            result = await news_service.search_company_news("Test Company", {})
            
            assert isinstance(result, NewsAnalysis)
            assert result.total_articles_found == 0
            assert len(result.articles) == 0
            assert result.overall_sentiment == 0.0
            assert result.positive_news.count == 0
            assert result.negative_news.count == 0

    @pytest.mark.asyncio
    async def test_search_company_news_with_results(self, news_service, sample_articles, mock_openai_response):
        """Test news search with actual results."""
        # Mock the web search
        with patch.object(news_service, '_perform_web_search', return_value=sample_articles):
            # Mock OpenAI analysis
            news_service.client.chat.completions.create.return_value = mock_openai_response
            
            result = await news_service.search_company_news("Test Company", {})
            
            assert isinstance(result, NewsAnalysis)
            assert result.total_articles_found > 0
            assert len(result.articles) > 0
            assert result.positive_news is not None
            assert result.negative_news is not None

    @pytest.mark.asyncio
    async def test_search_company_news_caching(self, news_service, sample_articles, mock_openai_response):
        """Test news search caching mechanism."""
        with patch.object(news_service, '_perform_web_search', return_value=sample_articles) as mock_search:
            news_service.client.chat.completions.create.return_value = mock_openai_response
            
            # First call
            result1 = await news_service.search_company_news("Test Company", {})
            
            # Second call should use cache
            result2 = await news_service.search_company_news("Test Company", {})
            
            # Search should only be called once due to caching
            assert mock_search.call_count == 1
            assert result1.summary == result2.summary

    @pytest.mark.asyncio
    async def test_search_company_news_error_handling(self, news_service):
        """Test error handling in news search."""
        with patch.object(news_service, '_perform_web_search', side_effect=Exception("Search failed")):
            result = await news_service.search_company_news("Test Company", {})
            
            assert isinstance(result, NewsAnalysis)
            assert result.total_articles_found == 0
            assert "technical issues" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_analyze_article_success(self, news_service, mock_openai_response):
        """Test successful article analysis."""
        news_service.client.chat.completions.create.return_value = mock_openai_response
        
        article = {
            'title': 'Test Company shows strong growth',
            'content': 'The company reported excellent results this quarter.',
            'source': 'fd.nl',
            'date': datetime.now(),
            'url': 'https://test.com/article'
        }
        
        result = await news_service._analyze_article(article, "Test Company")
        
        assert isinstance(result, NewsArticle)
        assert result.title == article['title']
        assert result.source == article['source']
        assert -1.0 <= result.sentiment_score <= 1.0
        assert 0.0 <= result.relevance_score <= 1.0
        assert len(result.categories) > 0
        assert len(result.key_phrases) >= 0

    @pytest.mark.asyncio
    async def test_analyze_article_openai_error(self, news_service):
        """Test article analysis with OpenAI error."""
        news_service.client.chat.completions.create.side_effect = Exception("OpenAI error")
        
        article = {
            'title': 'Test article',
            'content': 'Test content',
            'source': 'test.com',
            'date': datetime.now()
        }
        
        result = await news_service._analyze_article(article, "Test Company")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_article_json_parsing_error(self, news_service):
        """Test article analysis with malformed JSON response."""
        # Mock response with invalid JSON
        invalid_response = ChatCompletion(
            id="test-id",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    message=ChatCompletionMessage(
                        content="Invalid JSON response",
                        role="assistant"
                    )
                )
            ],
            created=1234567890,
            model="gpt-4.1",
            object="chat.completion",
            usage=CompletionUsage(
                completion_tokens=10,
                prompt_tokens=50,
                total_tokens=60
            )
        )
        
        news_service.client.chat.completions.create.return_value = invalid_response
        
        article = {
            'title': 'Test article',
            'content': 'Test content',
            'source': 'test.com',
            'date': datetime.now()
        }
        
        result = await news_service._analyze_article(article, "Test Company")
        
        # Should still return a result using fallback parsing
        assert isinstance(result, NewsArticle)
        assert result.sentiment_score == 0.0  # Default fallback
        assert result.relevance_score >= 0.0

    def test_generate_search_queries(self, news_service):
        """Test search query generation."""
        queries = news_service._generate_search_queries(
            "Test Company", "6m", include_positive=True, include_negative=True
        )
        
        assert len(queries) > 2
        assert any('Test Company' in query for query in queries)
        assert any('award' in query or 'success' in query for query in queries)
        assert any('lawsuit' in query or 'problems' in query for query in queries)

    def test_generate_search_queries_positive_only(self, news_service):
        """Test search query generation with positive only."""
        queries = news_service._generate_search_queries(
            "Test Company", "6m", include_positive=True, include_negative=False
        )
        
        assert len(queries) >= 2
        assert any('success' in query or 'award' in query for query in queries)
        assert not any('lawsuit' in query or 'problems' in query for query in queries)

    @pytest.mark.asyncio
    async def test_simulate_search_results(self, news_service):
        """Test simulated search results."""
        results = await news_service._simulate_search_results("Test Company", "6m")
        
        assert len(results) >= 0
        for result in results:
            assert 'title' in result
            assert 'content' in result
            assert 'source' in result
            assert 'date' in result

    def test_classify_categories(self, news_service):
        """Test article category classification."""
        # Test financial category
        financial_text = "The company reported strong revenue and profit growth"
        categories = news_service._classify_categories(financial_text)
        assert 'financial' in categories
        
        # Test legal category
        legal_text = "The company faces a lawsuit and legal investigation"
        categories = news_service._classify_categories(legal_text)
        assert 'legal' in categories
        
        # Test multiple categories
        mixed_text = "The company reported strong financial results but faces regulatory investigation"
        categories = news_service._classify_categories(mixed_text)
        assert 'financial' in categories
        assert 'regulatory' in categories

    def test_get_trust_score_for_source(self, news_service):
        """Test trust score calculation for sources."""
        # High trust Dutch source
        assert news_service._get_trust_score_for_source('fd.nl') == 1.0
        
        # High trust international source
        assert news_service._get_trust_score_for_source('reuters.com') == 1.0
        
        # Medium trust source
        assert news_service._get_trust_score_for_source('business-news.com') == 0.7
        
        # Unknown source
        assert news_service._get_trust_score_for_source('unknown-site.com') == 0.5
        
        # Empty source
        assert news_service._get_trust_score_for_source('') == 0.5

    def test_analyze_sentiment(self, news_service):
        """Test basic sentiment analysis."""
        # Positive text
        positive_text = "The company shows great success and excellent growth"
        sentiment = news_service.analyze_sentiment(positive_text)
        assert sentiment > 0
        
        # Negative text
        negative_text = "The company faces terrible problems and bad losses"
        sentiment = news_service.analyze_sentiment(negative_text)
        assert sentiment < 0
        
        # Neutral text
        neutral_text = "The company operates in the market"
        sentiment = news_service.analyze_sentiment(neutral_text)
        assert sentiment == 0.0

    def test_classify_relevance(self, news_service):
        """Test relevance classification."""
        article_high = {
            'title': 'Test Company announces new product',
            'content': 'Test Company has launched an innovative solution. Test Company expects strong market response.'
        }
        relevance = news_service.classify_relevance(article_high, 'Test Company')
        assert relevance > 0.6
        
        article_low = {
            'title': 'Market trends in technology',
            'content': 'Various technology trends are emerging in the market.'
        }
        relevance = news_service.classify_relevance(article_low, 'Test Company')
        assert relevance == 0.0

    def test_extract_key_phrases(self, news_service):
        """Test key phrase extraction."""
        text = "The technology company announced innovative solutions for digital transformation projects"
        phrases = news_service.extract_key_phrases(text)
        
        assert len(phrases) > 0
        assert all(len(phrase) > 3 for phrase in phrases)
        assert 'technology' in phrases or 'company' in phrases

    def test_cache_functionality(self, news_service):
        """Test caching functionality."""
        test_result = {'test': 'data'}
        cache_key = 'test_key'
        
        # Cache a result
        news_service._cache_result(cache_key, test_result, ttl_hours=1)
        
        # Retrieve from cache
        cached_result = news_service._get_cached_result(cache_key)
        assert cached_result == test_result
        
        # Test cache miss
        missing_result = news_service._get_cached_result('nonexistent_key')
        assert missing_result is None

    def test_generate_cache_key(self, news_service):
        """Test cache key generation."""
        key1 = news_service._generate_cache_key("Test Company", {"param1": "value1"})
        key2 = news_service._generate_cache_key("Test Company", {"param1": "value1"})
        key3 = news_service._generate_cache_key("Test Company", {"param1": "value2"})
        
        # Same parameters should generate same key
        assert key1 == key2
        
        # Different parameters should generate different keys
        assert key1 != key3
        
        # Keys should be valid MD5 hashes
        assert len(key1) == 32
        assert all(c in '0123456789abcdef' for c in key1)

    def test_get_usage_stats(self, news_service):
        """Test usage statistics."""
        # Set some usage stats
        news_service.total_requests = 10
        news_service.total_input_tokens = 1000
        news_service.total_output_tokens = 500
        
        stats = news_service.get_usage_stats()
        
        assert stats['total_requests'] == 10
        assert stats['total_input_tokens'] == 1000
        assert stats['total_output_tokens'] == 500
        assert stats['total_tokens'] == 1500
        assert 'estimated_cost_usd' in stats
        assert stats['estimated_cost_usd'] > 0

    @pytest.mark.asyncio
    async def test_generate_overall_analysis_mixed_sentiment(self, news_service):
        """Test overall analysis generation with mixed sentiment articles."""
        articles = [
            NewsArticle(
                title="Positive news",
                source="test.com",
                date=datetime.now(),
                summary="Good news about the company",
                sentiment_score=0.7,
                relevance_score=0.8,
                categories=['financial'],
                key_phrases=['growth', 'success'],
                trust_score=1.0,
                url="https://test.com/1"
            ),
            NewsArticle(
                title="Negative news",
                source="test.com",
                date=datetime.now(),
                summary="Bad news about legal issues",
                sentiment_score=-0.6,
                relevance_score=0.9,
                categories=['legal'],
                key_phrases=['lawsuit', 'investigation'],
                trust_score=1.0,
                url="https://test.com/2"
            )
        ]
        
        result = await news_service._generate_overall_analysis("Test Company", articles)
        
        assert isinstance(result, NewsAnalysis)
        assert result.positive_news.count == 1
        assert result.negative_news.count == 1
        assert result.total_articles_found == 2
        assert len(result.articles) == 2
        assert 'Legal Issues' in result.risk_indicators
        assert len(result.key_topics) > 0

    def test_parse_analysis_fallback(self, news_service):
        """Test fallback parsing when JSON parsing fails."""
        # Test with sentiment and relevance in text
        content = "The sentiment score is 0.7 and relevance is 0.8"
        result = news_service._parse_analysis_fallback(content)
        
        assert result['sentiment_score'] == 0.7
        assert result['relevance_score'] == 0.8
        
        # Test with no extractable values
        content = "This is just random text"
        result = news_service._parse_analysis_fallback(content)
        
        assert result['sentiment_score'] == 0.0
        assert result['relevance_score'] == 0.5