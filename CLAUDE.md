# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI-based business analysis API that provides automated due diligence for Dutch companies. The system works with **company names** and uses **Crawl4AI for intelligent web content analysis**, legal databases (rechtspraak.nl), and OpenAI for AI-driven news analysis to assess company risks. The improved workflow eliminates KvK API dependencies in favor of smart web crawling with boilerplate removal and content chunking.

## Core Architecture

The project follows a layered FastAPI architecture with **three main analysis endpoints**:

- **app/main.py**: FastAPI application with multiple analysis workflows
- **app/core/**: Configuration, logging, exceptions
- **app/models/**: Pydantic request/response models (name-based with contactpersoon support, includes WebContent models)
- **app/services/**: Business logic (CrawlService for web content, mandatory legal, Dutch-focused news)
- **app/api/**: API endpoints and dependencies
- **app/utils/**: Utilities (validators, rate limiting)

## Key Components

### Services Architecture
- **CrawlService**: Crawl4AI integration for intelligent web content analysis with Markdown output and boilerplate removal
- **LegalService**: MANDATORY Rechtspraak.nl Open Data API integration (always performed)
- **NewsService**: OpenAI-powered analysis focusing on Dutch news sources (FD, NRC, NOS, etc.)
- **RiskService**: Integrated risk assessment combining web content, legal, and news data

### Improved Workflow Data Flow
1. **Standard Analysis** (`/analyze-company`): Company name → Crawl4AI website analysis → Legal cases → News analysis → Risk assessment
2. **Nederlandse Analyse** (`/nederlands-bedrijf-analyse`): Company name + contactpersoon → Dutch website crawling → MANDATORY legal check → Dutch news priority → Structured output
3. **Simple Analysis** (`/analyze-company-simple`): Company name → Fast parallel processing (crawl + legal + news) → Simple JSON output

## Common Commands

### Development
```bash
# Start development server
uvicorn app.main:app --reload

# Run tests
pytest

# Code quality checks
black app/ tests/
isort app/ tests/
flake8 app/ tests/
mypy app/
```

### Installation
Based on technical requirements, install these core dependencies including Crawl4AI:
```bash
pip install fastapi==0.104.1 uvicorn[standard]==0.24.0 pydantic==2.5.0 httpx==0.25.2 beautifulsoup4==4.12.2 lxml==4.9.3 openai==1.3.0 python-decouple==3.8 structlog==23.2.0 tenacity==8.2.3 crawl4ai==0.3.74
```

## Implementation Phases

The project was implemented in the following phases (now completed):
1. **Phase 1**: Core infrastructure and FastAPI setup ✅
2. **Phase 2**: Crawl4AI integration for web content analysis ✅ 
3. **Phase 3**: Legal service (rechtspraak.nl integration) ✅
4. **Phase 4**: AI news analysis with OpenAI ✅
5. **Phase 5**: Integration, testing, and deployment ✅

## Key Requirements

### Performance
- Simple analysis: < 15 seconds response time
- Standard analysis: < 30 seconds response time
- Dutch analysis: < 40 seconds response time
- No persistent data storage (GDPR compliance)
- Rate limiting: 100 requests/hour per API key

### External API Integration
- **Crawl4AI**: Intelligent web crawling with Markdown output, configurable depth and robots.txt compliance
- **Rechtspraak.nl**: 1 request/second limit, respectful scraping
- **OpenAI**: GPT-4-turbo with function calling, 30s timeout

### Security
- API key authentication via X-API-Key header
- No sensitive data logging or storage
- HTTPS only, security headers enforced
- Input validation with Pydantic schemas

## Response Format

All endpoints return JSON with structured error handling:
- Success: HTTP 200 with CompanyAnalysisResponse
- Validation errors: HTTP 400 with error details
- Not found: HTTP 404 for invalid company data
- Rate limit: HTTP 429 with retry information
- Server errors: HTTP 500 with correlation IDs

## Environment Configuration

Required environment variables:
```bash
OPENAI_API_KEY=your_openai_key
APP_NAME=bedrijfsanalyse-api
DEBUG=false
LOG_LEVEL=INFO

# Optional Crawl4AI configuration
CRAWL_TIMEOUT=30
CRAWL_MAX_DEPTH_STANDARD=2
CRAWL_MAX_DEPTH_SIMPLE=1
CRAWL_OBEY_ROBOTS_TXT=true
```

## Testing Strategy

- Unit tests with pytest and pytest-asyncio
- Mock all external API calls (Crawl4AI, OpenAI, rechtspraak.nl)
- Integration tests for complete request/response flows
- Error scenario testing for resilience
- Performance testing for response time requirements