# Stap 3: Legal Service Implementatie (Rechtspraak.nl)

## Doel
Implementeer web scraping service voor rechtspraak.nl om automatisch juridische uitspraken en rechtszaken op te halen die gerelateerd zijn aan bedrijven.

## Voorbereidingen
- Stap 1 en 2 volledig afgerond
- KvK integratie werkend
- Web scraping dependencies (BeautifulSoup, lxml) beschikbaar

## Prompts voor implementatie

### 3.1 Legal Service basis implementatie
**Prompt**: "Implementeer app/services/legal_service.py met een LegalService class die:

1. Web scraping setup met httpx + BeautifulSoup:
   - Base URL: https://www.rechtspraak.nl/
   - Respecteer robots.txt en rate limits (1 request/second)
   - Custom User-Agent met identificatie
   - Timeout configuratie (RECHTSPRAAK_TIMEOUT)
   - Session management voor cookies

2. Core methodes:
   - search_company_cases(company_name: str, trade_name: str = None) -> List[LegalCase]
   - get_case_details(ecli: str) -> LegalCaseDetail
   - parse_search_results(html: str) -> List[Dict]
   - extract_case_info(case_url: str) -> Dict

3. Respecteer technische requirements:
   - Rate limiting: max 1 request per seconde
   - Graceful error handling voor 404, timeouts, parsing errors
   - Retry logic met exponential backoff"

### 3.2 Legal data models
**Prompt**: "Maak legal data models in app/models/response_models.py:

1. LegalCase model:
   - ecli: str
   - case_number: str  
   - date: datetime
   - court: str
   - type: str (civil, criminal, administrative)
   - parties: List[str]
   - summary: str
   - outcome: str (won, lost, partial, unknown)
   - url: str
   - relevance_score: float (0.0-1.0)

2. LegalFindings model:
   - total_cases: int
   - risk_level: str (low, medium, high)
   - cases: List[LegalCase]

3. Gebruik Pydantic validators voor data cleaning"

### 3.3 Rechtspraak.nl scraping logica
**Prompt**: "Implementeer specifieke rechtspraak.nl scraping functies:

1. Search query builder:
   - Zoek op bedrijfsnaam en handelsnaam
   - Filter op relevante rechtbank types
   - Datum filtering (configureerbaar bereik)
   - Pagination handling

2. HTML parsing functies:
   - parse_search_page(): extract case links en basis info
   - parse_case_detail(): extract ECLI, partijen, samenvatting
   - extract_court_info(): identificeer rechtbank en type zaak
   - clean_text_content(): normalize text data

3. Data extraction:
   - ECLI parsing en validatie
   - Datum extractie en parsing
   - Partijen identificatie (focus op bedrijfsnamen)
   - Case type classificatie"

### 3.4 Company name matching
**Prompt**: "Implementeer company matching logic in app/utils/text_utils.py:

1. Name similarity functions:
   - normalize_company_name(): clean bedrijfsnamen
   - calculate_similarity(): string matching score
   - extract_legal_forms(): herken B.V., N.V., etc.
   - match_company_variations(): handel variaties in namen

2. Relevance scoring:
   - Exact name match: 1.0
   - Partial match met legal form: 0.8
   - Trade name match: 0.7
   - Partial match zonder legal form: 0.5
   - Minimum threshold: 0.6

3. False positive filtering:
   - Filter common company names
   - Exclude cases waar bedrijf alleen als referentie genoemd"

### 3.5 Legal risk assessment
**Prompt**: "Implementeer risk scoring in app/services/legal_service.py:

1. Risk calculation methode:
   - assess_legal_risk(cases: List[LegalCase]) -> str
   - Factor in: aantal cases, type cases, outcomes, recentheid
   - Risk levels: low (0-2 cases), medium (3-5), high (6+)

2. Risk factors:
   - Criminal cases: high impact
   - Multiple civil losses: medium-high impact  
   - Recent cases (< 2 jaar): higher weight
   - Won cases: lower impact
   - Administrative cases: lower impact

3. Risk recommendations:
   - Genereer specifieke aanbevelingen per risk level
   - Actionable items voor monitoring/mitigation"

### 3.6 Robots.txt compliance
**Prompt**: "Implementeer robots.txt compliance in app/utils/web_utils.py:

1. Robots checker:
   - fetch_robots_txt(base_url: str) -> str
   - parse_robots_rules(robots_txt: str) -> Dict
   - is_path_allowed(url: str, user_agent: str) -> bool
   - get_crawl_delay(robots_txt: str) -> int

2. Integration in LegalService:
   - Check robots.txt bij service startup
   - Respecteer crawl-delay directives
   - Skip disallowed paths
   - Log compliance status"

### 3.7 Caching en performance
**Prompt**: "Implementeer caching voor legal service:

1. In-memory cache:
   - Cache search results (30 min TTL)
   - Cache case details (24 hour TTL)
   - LRU eviction policy
   - Cache key: hash van company name + filters

2. Performance optimizations:
   - Concurrent requests (max 3 simultaan)
   - Request pooling met httpx
   - Response compression handling
   - Smart pagination (stop bij irrelevante results)

3. Monitoring:
   - Track cache hit rates
   - Monitor response times
   - Alert op parsing failures"

### 3.8 Legal service tests
**Prompt**: "Maak uitgebreide tests in tests/test_services/test_legal_service.py:

1. HTML parsing tests:
   - Mock rechtspraak.nl HTML responses
   - Test various case formats en edge cases
   - Test ECLI extraction en validation
   - Test company name matching accuracy

2. Web scraping tests:
   - Mock httpx requests
   - Test rate limiting compliance
   - Test timeout handling
   - Test robots.txt compliance

3. Integration tests:
   - Full search flow tests
   - Risk assessment validation
   - Error handling scenarios"

### 3.9 Legal endpoint integratie
**Prompt**: "Update app/api/endpoints/analyze.py om legal service te integreren:

1. Extend CompanyAnalysisResponse:
   - Voeg legal_findings field toe
   - Include legal risk in overall risk assessment

2. Service orchestration:
   - Parallel execution van KvK en Legal services
   - Graceful degradation bij legal service failures
   - Timeout handling (max 30s voor standard, 45s voor deep)

3. Error handling:
   - Legal service failures niet blokkend voor KvK data
   - Partial results bij timeouts
   - Clear error messages in response"

### 3.10 Legal compliance en ethiek
**Prompt**: "Implementeer legal compliance measures:

1. Fair use policies:
   - Rate limiting enforcement
   - User-Agent identificatie
   - No aggressive crawling
   - Respect for site terms

2. Data handling:
   - No persistent storage van legal data
   - Privacy-aware logging (geen persoonlijke data)
   - GDPR compliance voor publieke rechtspraak data

3. Monitoring en alerting:
   - Monitor voor blocked requests
   - Alert bij hoge failure rates
   - Track compliance metrics"

## Verwacht resultaat
- Werkende legal service met rechtspraak.nl integratie
- Company matching en relevance scoring
- Legal risk assessment
- Robots.txt compliance
- Performance optimizations
- Uitgebreide test coverage
- Integratie in /analyze-company endpoint

## Verificatie
```bash
# Test legal service integratie
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "kvk_number": "69599084",
    "search_depth": "standard"
  }'

# Test met bekend bedrijf met rechtszaken
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "kvk_number": "12345678",
    "search_depth": "deep"
  }'

# Run legal service tests
pytest tests/test_services/test_legal_service.py -v --cov=app/services/legal_service

# Test robots.txt compliance
python -c "
from app.utils.web_utils import is_path_allowed
print(is_path_allowed('https://www.rechtspraak.nl/Uitspraken/', '*'))
"
```

## Test scenarios
1. **Bedrijf met rechtszaken**: Test met bekende bedrijfsnamen
2. **Bedrijf zonder rechtszaken**: Verwacht lege results
3. **Rate limiting**: Test 1 request/second enforcement
4. **Error handling**: Mock network errors, parsing failures
5. **Company matching**: Test name variations en false positives

## Performance targets
- Search response: < 15 seconden (standard), < 30 seconden (deep)
- Relevance accuracy: > 80% voor gevonden cases
- Cache hit rate: > 60% voor repeat searches
- Rate limit compliance: 100%

## Monitoring
- Legal service response times
- Case parsing success rates
- Company match accuracy
- Robots.txt compliance status
- Cache performance metrics

## Volgende stap
Na succesvolle completie van stap 3, ga naar stap4.md voor AI News Analysis Service implementatie.