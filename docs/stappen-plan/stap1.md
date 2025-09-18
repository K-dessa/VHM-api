# Stap 1: Project Setup en Basis Infrastructure

## Doel
Opzetten van de basis FastAPI applicatie met alle benodigde dependencies, project structuur en configuratie.

## Prompts voor implementatie

### 1.1 Dependencies installeren
```bash
# Installeer alle core dependencies uit technical-requirements.md
pip install fastapi==0.104.1 uvicorn[standard]==0.24.0 pydantic==2.5.0 httpx==0.25.2 beautifulsoup4==4.12.2 lxml==4.9.3 openai==1.3.0 python-decouple==3.8 structlog==23.2.0 tenacity==8.2.3

# Installeer development dependencies
pip install pytest==7.4.3 pytest-asyncio==0.21.1 black==23.11.0 isort==5.12.0 mypy==1.7.0 flake8==6.1.0 pre-commit==3.5.0

# Genereer requirements.txt
pip freeze > requirements.txt
```

### 1.2 Project structuur aanmaken
```
Maak de volgende mappenstructuur aan:
app/
├── __init__.py
├── main.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── logging.py
│   └── exceptions.py
├── models/
│   ├── __init__.py
│   ├── request_models.py
│   └── response_models.py
├── services/
│   ├── __init__.py
│   ├── kvk_service.py
│   └── news_service.py
├── api/
│   ├── __init__.py
│   ├── dependencies.py
│   └── endpoints/
│       ├── __init__.py
│       ├── analyze.py
│       └── health.py
└── utils/
    ├── __init__.py
    ├── validators.py
    └── rate_limiter.py

tests/
├── __init__.py
├── test_main.py
├── test_services/
├── test_api/
└── fixtures/
```

### 1.3 Basis configuratie setup
**Prompt**: "Maak een config.py bestand in app/core/ met de volgende environment variabelen uit technical-requirements.md:
- APP_NAME, APP_VERSION, DEBUG, LOG_LEVEL
- KVK_API_KEY, OPENAI_API_KEY  
- RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW
- KVK_TIMEOUT, RECHTSPRAAK_TIMEOUT, OPENAI_TIMEOUT

Gebruik python-decouple voor environment management en maak een Settings class met pydantic BaseSettings."

### 1.4 Structured logging setup
**Prompt**: "Implementeer structured logging in app/core/logging.py met structlog. Configureer JSON output, correlation IDs en log levels. Maak een get_logger functie die gebruikt kan worden door andere modules."

### 1.5 Exception handling
**Prompt**: "Maak custom exceptions in app/core/exceptions.py voor:
- ValidationError
- ExternalAPIError (met subklasses voor KvK, OpenAI)
- RateLimitError
- CompanyNotFoundError
- TimeoutError

Implementeer ook een global exception handler in main.py die deze exceptions vertaalt naar de juiste HTTP responses volgens api-specifications.md."

### 1.6 Request/Response models
**Prompt**: "Maak Pydantic models in app/models/ voor alle request en response schemas uit api-specifications.md:

request_models.py:
- CompanyAnalysisRequest
- SearchDepth enum
- DateRange enum

response_models.py:
- CompanyInfo
- NewsAnalysis
- RiskAssessment
- CompanyAnalysisResponse
- ErrorResponse
- HealthResponse"

### 1.7 Main FastAPI app setup
**Prompt**: "Update app/main.py om:
1. FastAPI app te configureren met metadata uit project-overview.md
2. CORS middleware toe te voegen (restrictive)
3. Request size limiting (max 1MB)
4. Security headers middleware
5. Exception handlers toe te voegen
6. Request logging middleware
7. Include routers voor /analyze-company, /health, /status endpoints"

### 1.8 Health check endpoint
**Prompt**: "Implementeer /health endpoint in app/api/endpoints/health.py volgens api-specifications.md. Check connectivity naar:
- KvK API (test call)
- OpenAI API (test call)

Return status healthy/unhealthy/degraded met dependency statuses."

### 1.9 Environment configuratie
**Prompt**: "Maak een .env.example bestand met alle environment variabelen uit technical-requirements.md (zonder echte keys). Maak ook een docker-compose.yml voor lokale development."

### 1.10 Basic testing setup
**Prompt**: "Maak basis test setup in tests/:
- conftest.py met fixtures voor FastAPI test client
- test_main.py voor basic app tests
- test_health.py voor health endpoint
- Mock fixtures voor externe APIs"

## Verwacht resultaat
- Werkende FastAPI applicatie met alle endpoints (nog zonder implementatie)
- Alle dependencies geïnstalleerd  
- Correcte project structuur
- Configuratie via environment variables
- Structured logging
- Exception handling
- Basic tests
- Health check endpoint werkend

## Verificatie
```bash
# Start de applicatie
uvicorn app.main:app --reload

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/status

# Run tests
pytest

# Code quality checks
black app/ tests/
isort app/ tests/
flake8 app/ tests/
mypy app/
```

## Volgende stap
Na succesvolle completie van stap 1, ga naar stap2.md voor KvK API integratie.