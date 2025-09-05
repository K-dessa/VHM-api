# Stap 2: KvK API Integratie

## Doel
Implementeer volledige KvK (Kamer van Koophandel) API integratie voor het ophalen van bedrijfsinformatie op basis van KvK-nummers.

## Voorbereidingen
- Zorg dat stap 1 volledig is afgerond
- KvK API key beschikbaar in environment variabelen
- Basis project structuur staat

## Prompts voor implementatie

### 2.1 KvK Service implementatie
**Prompt**: "Implementeer app/services/kvk_service.py met een KvKService class die:

1. KvK API client setup met httpx:
   - Base URL: https://developers.kvk.nl/
   - API key authenticatie via header
   - Timeout configuratie uit settings (KVK_TIMEOUT)
   - Rate limiting respect (500 requests/day)

2. Methodes implementeert:
   - get_company_info(kvk_number: str) -> CompanyInfo
   - validate_kvk_number(kvk_number: str) -> bool
   - _make_api_request() met retry logic (tenacity)
   - _handle_api_errors() voor error mapping

3. Error handling voor:
   - Invalid KvK number format
   - Company not found (404)
   - Rate limits exceeded (429) 
   - API timeouts
   - Network errors

Gebruik de bestaande config en exception classes uit stap 1."

### 2.2 KvK number validator
**Prompt**: "Implementeer in app/utils/validators.py een validate_kvk_number functie die:
- Controleert of KvK nummer exact 8 cijfers is
- Basis modulus 11 check (als beschikbaar in KvK specificatie)
- Geeft duidelijke error messages
- Werkt samen met Pydantic field validation"

### 2.3 CompanyInfo model uitbreiden
**Prompt**: "Breid het CompanyInfo model uit in app/models/response_models.py met alle velden uit api-specifications.md:
- kvk_number, name, trade_name, legal_form
- Address nested model (street, postal_code, city, country)
- status, establishment_date
- SBI codes list met code en description
- employee_count, website
- Gebruik correcte Pydantic types en validators"

### 2.4 KvK API endpoint implementatie
**Prompt**: "Implementeer in app/api/endpoints/analyze.py een basis versie van POST /analyze-company die:
1. CompanyAnalysisRequest valideert
2. KvK number extraheert en valideert
3. KvKService aanroept voor bedrijfsgegevens
4. Basis CompanyAnalysisResponse retourneert (alleen company_info gevuld)
5. Correcte HTTP status codes gebruikt
6. Error responses volgens api-specifications.md format"

### 2.5 Rate limiting implementatie
**Prompt**: "Implementeer rate limiting in app/utils/rate_limiter.py:
1. In-memory rate limiter class (later Redis ready)
2. Rate limiting per API key
3. Headers toevoegen: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
4. HTTP 429 response bij overschrijding
5. Configureerbaar via settings (RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)"

### 2.6 API key authenticatie
**Prompt**: "Implementeer API key authenticatie in app/api/dependencies.py:
1. get_api_key dependency function
2. X-API-Key header validatie
3. Basic API key checking (hardcoded lijst voor nu)
4. HTTP 401 voor missing/invalid keys
5. HTTP 403 voor unauthorized access"

### 2.7 KvK Service tests
**Prompt**: "Maak uitgebreide tests in tests/test_services/test_kvk_service.py:
1. Mock KvK API responses met httpx_mock
2. Test happy path - valid company found
3. Test error cases: invalid KvK, not found, timeout, rate limit
4. Test retry logic bij netwerkfouten
5. Test data mapping naar CompanyInfo model
6. Fixtures voor common test data"

### 2.8 Integration tests
**Prompt**: "Maak integration tests in tests/test_api/test_analyze_endpoint.py:
1. Test complete /analyze-company flow
2. Mock KvK service
3. Test request validation errors
4. Test authentication/authorization
5. Test rate limiting
6. Test response format compliance"

### 2.9 Environment configuratie
**Prompt**: "Update .env.example met:
- KVK_API_KEY=your_kvk_api_key_here
- KVK_BASE_URL=https://developers.kvk.nl/
- KVK_TIMEOUT=10
- API_KEYS=key1,key2,key3 (voor basic auth)

Update app/core/config.py om deze settings te laden."

### 2.10 Error monitoring
**Prompt**: "Voeg uitgebreide logging toe aan KvKService:
1. Request/response logging (zonder sensitive data)
2. Error logging met correlation IDs
3. Performance metrics (response times)
4. Rate limit warnings
5. API quota monitoring

Gebruik de structured logger uit stap 1."

### 2.11 Documentation
**Prompt**: "Update API documentatie:
1. FastAPI automatic OpenAPI docs configureren
2. Request/response examples toevoegen
3. Error codes documenteren
4. Usage examples in OpenAPI schema
5. KvK API dependency documenteren"

## Verwacht resultaat
- Werkende KvK API integratie
- POST /analyze-company endpoint geeft KvK bedrijfsgegevens terug
- Correcte error handling en responses
- Rate limiting geïmplementeerd
- API key authenticatie werkend
- Uitgebreide test coverage
- Performance monitoring

## Verificatie
```bash
# Test KvK integratie
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"kvk_number": "69599084"}'

# Test error cases
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"kvk_number": "invalid"}'

# Test rate limiting
for i in {1..105}; do curl -X POST ...; done

# Run tests
pytest tests/test_services/test_kvk_service.py -v
pytest tests/test_api/test_analyze_endpoint.py -v
```

## Test data
Voor testing gebruik bekende KvK nummers zoals:
- 69599084 (bestaand bedrijf)
- 12345678 (niet bestaand, voor 404 testing)

## Troubleshooting
- KvK API documentatie: https://developers.kvk.nl/documentation
- Check API key geldigheid
- Monitor rate limits (500 requests/day free tier)
- Test eerst met KvK API test environment

## Volgende stap
Na succesvolle completie van stap 2, ga naar stap3.md voor Legal Service implementatie.