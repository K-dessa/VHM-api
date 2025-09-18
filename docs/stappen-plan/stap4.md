# Stap 4: AI News Analysis Service (OpenAI Integration)

## Doel
Implementeer AI-gedreven nieuwsanalyse met OpenAI function calling voor het zoeken, analyseren en classificeren van nieuws artikelen over bedrijven.

## Voorbereidingen
- Stap 1, 2 en 3 volledig afgerond
- OpenAI API key beschikbaar
- KvK service werkend

## Prompts voor implementatie

### 4.1 OpenAI Service basis setup
**Prompt**: "Implementeer app/services/news_service.py met een NewsService class die:

1. OpenAI client setup:
   - OpenAI API client met httpx backend
   - API key via environment variable
   - Model: GPT-4-turbo (gpt-4.1)
   - Temperature: 0.1 voor consistente resultaten
   - Timeout: OPENAI_TIMEOUT uit config

2. Core service methodes:
   - search_company_news(company_name: str, search_params: dict) -> NewsAnalysis
   - analyze_sentiment(text: str) -> float
   - classify_relevance(article: dict, company: str) -> float
   - extract_key_phrases(text: str) -> List[str]

3. Token management:
   - Input token counting en limits (128k max)
   - Output token limits (4k max)
   - Cost tracking en monitoring
   - Efficient prompt engineering"

### 4.2 OpenAI Function Calling setup
**Prompt**: "Implementeer OpenAI function calling voor web search:

1. Function definitions in app/services/openai_functions.py:
   ```python
   web_search_function = {
       'name': 'web_search',
       'description': 'Search the web for recent news about a company',
       'parameters': {
           'type': 'object',
           'properties': {
               'query': {'type': 'string'},
               'date_range': {'type': 'string'},
               'language': {'type': 'string'},
               'max_results': {'type': 'integer'}
           },
           'required': ['query']
       }
   }
   ```

2. Function handlers:
   - handle_web_search(): execute search queries
   - format_search_results(): structure results voor AI analysis
   - filter_relevant_sources(): prioritize trusted news sources

3. Search integration:
   - Multiple search strategies (broad + specific)
   - Date range filtering
   - Source quality filtering
   - Deduplication logic"

### 4.3 News search implementation
**Prompt**: "Implementeer web search functionaliteit:

1. Search query generation:
   - Company name variations (official name, trade names)
   - Positive search terms: 'award', 'growth', 'expansion', 'success'
   - Negative search terms: 'lawsuit', 'bankruptcy', 'scandal', 'problems'
   - Date range queries: 'last year', 'recent months'

2. Search execution:
   - Use multiple search engines/APIs (DuckDuckGo, Bing, etc.)
   - Fallback mechanisms bij API failures
   - Rate limiting per search service
   - Result aggregation en deduplication

3. Content extraction:
   - Fetch article full text waar mogelijk
   - Handle paywalls gracefully (summary only)
   - Extract metadata: publish date, author, source
   - Clean en normalize content"

### 4.4 News analysis models
**Prompt**: "Maak news analysis models in app/models/response_models.py:

1. NewsArticle model:
   - title: str
   - source: str
   - date: datetime
   - url: str
   - summary: str (AI-generated)
   - sentiment_score: float (-1.0 to 1.0)
   - relevance_score: float (0.0 to 1.0)
   - categories: List[str]
   - key_phrases: List[str]

2. NewsAnalysis model:
   - positive_news: PositiveNews (count, average_sentiment, articles)
   - negative_news: NegativeNews (count, average_sentiment, articles)
   - overall_sentiment: float
   - total_relevance: float

3. Validation en constraints:
   - Sentiment scores binnen range
   - Required fields validation
   - URL format validation"

### 4.5 Sentiment analysis prompt engineering
**Prompt**: "Ontwikkel geoptimaliseerde prompts voor sentiment analyse:

1. System prompt voor nieuws analyse:
   ```
   You are a business intelligence analyst specializing in company reputation analysis.
   Analyze news articles and extract:
   1. Sentiment score (-1.0 to 1.0)
   2. Relevance to the company (0.0 to 1.0)
   3. Key business impact phrases
   4. Article categories (financial, operational, etc.)
   
   Be objective and focus on business implications.
   ```

2. Few-shot examples:
   - Include examples van positive, negative, en neutral articles
   - Show proper sentiment scoring
   - Demonstrate relevance assessment

3. Output format specifications:
   - Structured JSON output
   - Consistent field naming
   - Error handling voor incomplete data"

### 4.6 Content filtering en quality control
**Prompt**: "Implementeer content filtering in app/utils/content_filter.py:

1. Source quality assessment:
   - Trusted news sources lijst (NOS, FD, etc.)
   - Domain reputation scoring
   - Exclude spam/low-quality sources
   - Social media content filtering

2. Content relevance filtering:
   - Company name mention verification
   - Context relevance (not just passing mention)
   - Language detection (focus op NL/EN)
   - Duplicate content detection

3. Quality thresholds:
   - Minimum relevance score: 0.6
   - Minimum article length: 100 words
   - Maximum age: configureerbaar via date_range
   - Source diversity (max 3 articles per source)"

### 4.7 News search optimization
**Prompt**: "Implementeer search optimization strategies:

1. Multi-stage search approach:
   - Stage 1: Broad search met company name
   - Stage 2: Specific searches voor positive/negative
   - Stage 3: Deep search voor financial terms

2. Search query optimization:
   - Company name synonyms en abbreviations
   - Industry-specific terms toevoegen
   - Location-based search (company city)
   - Language-specific queries

3. Result aggregation:
   - Score-based ranking
   - Date recency weighting  
   - Source authority weighting
   - Diversity optimization (verschillende aspecten)"

### 4.8 Caching en performance
**Prompt**: "Implementeer caching voor news service:

1. Multi-level caching:
   - OpenAI response cache (24 hour TTL)
   - Search results cache (6 hour TTL)
   - Sentiment analysis cache (persistent)

2. Cache strategies:
   - Cache key: hash van (company_name + search_params + date)
   - Intelligent cache invalidation
   - Cache size limits (LRU eviction)
   - Cache warming voor frequent requests

3. Performance optimizations:
   - Batch OpenAI requests waar mogelijk
   - Parallel search execution
   - Lazy loading van article content
   - Smart timeout handling"

### 4.9 News service tests
**Prompt**: "Maak uitgebreide tests in tests/test_services/test_news_service.py:

1. OpenAI integration tests:
   - Mock OpenAI API responses
   - Test function calling scenarios
   - Test sentiment analysis accuracy
   - Token usage monitoring

2. Search functionality tests:
   - Mock search API responses
   - Test query generation logic
   - Test result filtering en ranking
   - Test error handling scenarios

3. Content analysis tests:
   - Test sentiment scoring consistency
   - Test relevance assessment
   - Test category classification
   - Test key phrase extraction"

### 4.10 Integration en orchestration
**Prompt**: "Update app/api/endpoints/analyze.py voor news service integratie:

1. Service orchestration:
   - Parallel execution: KvK + News
   - Progressive loading (toon partial results)
   - Timeout management per service
   - Graceful degradation strategies

2. Search depth handling:
   - Standard: basis news search (5-10 articles)
   - Deep: uitgebreide search (15-25 articles)
   - Different timeout limits per depth

3. Response assembly:
   - Combine alle service results
   - Calculate overall risk assessment
   - Generate integrated recommendations
   - Include metadata over data freshness"

### 4.11 AI prompt optimization
**Prompt**: "Optimaliseer AI prompts voor efficiency:

1. Token efficiency:
   - Minimize prompt length
   - Use structured output formats
   - Efficient few-shot examples
   - Smart context truncation

2. Consistency optimization:
   - Standardized scoring rubrics
   - Clear output format specifications  
   - Consistent terminology
   - Error handling instructions

3. Quality assurance:
   - Prompt testing framework
   - A/B testing voor prompt variations
   - Quality metrics tracking
   - Human evaluation benchmarks"

### 4.12 Cost monitoring
**Prompt**: "Implementeer OpenAI cost monitoring:

1. Token tracking:
   - Input/output token counting
   - Cost calculation per request
   - Daily/monthly cost limits
   - Usage alerts en notifications

2. Optimization strategies:
   - Efficient prompt engineering
   - Smart caching to reduce calls
   - Batch processing waar mogelijk
   - Fallback strategies bij cost limits

3. Monitoring dashboard:
   - Real-time cost tracking
   - Usage patterns analysis
   - Cost per customer/request
   - Optimization recommendations"

## Verwacht resultaat
- Werkende AI news analysis service
- OpenAI function calling geïmplementeerd
- Sentiment analysis en relevance scoring
- Content filtering en quality control
- Cost-efficient token usage
- Comprehensive test coverage
- Integration in /analyze-company endpoint

## Verificatie
```bash
# Test news analysis
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "kvk_number": "69599084",
    "search_depth": "deep",
    "include_positive": true,
    "include_negative": true,
    "date_range": "6m"
  }'

# Test cost tracking
curl -X GET "http://localhost:8000/status" \
  -H "X-API-Key: test-key"

# Run news service tests
pytest tests/test_services/test_news_service.py -v --cov=app/services/news_service

# Test OpenAI integration
python -c "
from app.services.news_service import NewsService
service = NewsService()
result = service.search_company_news('Test Company B.V.', {})
print(f'Found {len(result.positive_news.articles)} positive articles')
"
```

## Performance targets
- News search: < 20 seconden (standard), < 40 seconden (deep)
- Sentiment accuracy: > 85% agreement met human evaluation
- Relevance filtering: < 10% false positives
- OpenAI cost: < €0.50 per standard search
- Cache hit rate: > 70% voor repeat searches

## Quality metrics
- Sentiment consistency score
- Relevance precision/recall
- Source diversity index
- Content quality score
- User satisfaction feedback

## Cost optimization
- Target: < €100/month voor 1000 searches
- Monitor token usage trends
- Implement cost alerts
- Optimize prompts voor efficiency
- Use caching aggressively

## Volgende stap
Na succesvolle completie van stap 4, ga naar stap5.md voor Integration & Testing.