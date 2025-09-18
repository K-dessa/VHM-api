# API Specification

## Base Information

- **Base URL**: `https://api.bedrijfsanalyse.nl/v1`
- **Protocol**: HTTPS only
- **Content-Type**: `application/json`
- **Authentication**: API Key via `X-API-Key` header

## Endpoints

### 1. Company Analysis (Name-Based)

#### `POST /analyze-company`

Analyseert een bedrijf op basis van **bedrijfsnaam** (KvK-nummer optioneel) en retourneert juridische en nieuws informatie.

**Request Headers**
```http
Content-Type: application/json
X-API-Key: your-api-key-here
```

**Request Body**
```json
{
  "company_name": "ASML Holding N.V.",
  "kvk_nummer": "17014545",
  "contactpersoon": "Peter Wennink",
  "search_depth": "standard",
  "news_date_range": "last_year",
  "include_subsidiaries": false
}
```

**Request Schema**
```json
{
  "type": "object",
  "required": ["company_name"],
  "properties": {
    "company_name": {
      "type": "string",
      "minLength": 2,
      "maxLength": 200,
      "description": "Juridische bedrijfsnaam van het bedrijf"
    },
    "kvk_nummer": {
      "type": "string",
      "pattern": "^[0-9]{8}$",
      "description": "8-digit KvK number (optional)"
    },
    "contactpersoon": {
      "type": "string",
      "maxLength": 100,
      "description": "Naam van contactpersoon om ook in nieuws/rechtszaken te zoeken"
    },
    "search_depth": {
      "type": "string",
      "enum": ["standard", "deep"],
      "default": "standard",
      "description": "Search intensity level"
    },
    "date_range": {
      "type": "string", 
      "enum": ["1m", "3m", "6m", "1y", "2y"],
      "default": "1y",
      "description": "Time range for news search"
    },
    "include_positive": {
      "type": "boolean",
      "default": true,
      "description": "Include positive news analysis"
    },
    "include_negative": {
      "type": "boolean", 
      "default": true,
      "description": "Include negative news analysis"
    },
    "language": {
      "type": "string",
      "enum": ["nl", "en"],
      "default": "nl",
      "description": "Response language"
    }
  }
}
```

**Response - Success (200)**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-09-04T10:30:00.000Z",
  "processing_time_ms": 25430,
  "company_info": {
    "kvk_number": "12345678",
    "name": "Example B.V.",
    "trade_name": "Example Company",
    "legal_form": "Besloten vennootschap",
    "address": {
      "street": "Voorbeeldstraat 1",
      "postal_code": "1234AB", 
      "city": "Amsterdam",
      "country": "Nederland"
    },
    "status": "active",
    "establishment_date": "2010-05-15",
    "sbi_codes": [
      {
        "code": "62010",
        "description": "Ontwikkelen, produceren en uitgeven van software"
      }
    ],
    "employee_count": "10-49",
    "website": "https://example.com"
  },
  "news_analysis": {
    "positive_news": {
      "count": 5,
      "average_sentiment": 0.7,
      "total_relevance": 0.8,
      "articles": [
        {
          "title": "Example B.V. wint innovatie award 2024",
          "source": "TechNews Nederland",
          "date": "2024-08-15",
          "url": "https://technews.nl/example-innovation-award",
          "summary": "Het bedrijf won de prestigieuze innovatie award voor hun nieuwe AI-platform",
          "sentiment_score": 0.85,
          "relevance_score": 0.9,
          "categories": ["innovation", "awards", "technology"],
          "key_phrases": ["innovatie award", "AI-platform", "technologie"]
        }
      ]
    },
    "negative_news": {
      "count": 1,
      "average_sentiment": -0.4,
      "total_relevance": 0.6,
      "articles": [
        {
          "title": "Klanten klagen over service Example B.V.",
          "source": "Consumentenbond",
          "date": "2024-06-10",
          "url": "https://consumentenbond.nl/klachten-example",
          "summary": "Meerdere klanten rapporteren vertragingen in service delivery",
          "sentiment_score": -0.4,
          "relevance_score": 0.6,
          "categories": ["customer_service", "complaints"],
          "key_phrases": ["klanten klagen", "service vertragingen"]
        }
      ]
    }
  },
  "risk_assessment": {
    "overall_score": "medium",
    "scores": {
      "reputation_risk": "low",
      "financial_risk": "low",
      "operational_risk": "low"
    },
    "factors": [
      {
      },
      {
        "category": "reputation", 
        "impact": "low",
        "description": "Overwegend positieve berichtgeving met enkele servicecomplaints"
      }
    ],
    "recommendations": [
      "Monitor lopende rechtszaken voor ontwikkelingen",
      "Verbeter customer service processen",
      "Kapitaliseer op recente innovatie award"
    ]
  },
  "metadata": {
    "search_parameters": {
      "depth": "standard",
      "date_range": "1y",
      "sources_checked": 15,
      "queries_executed": 8
    },
    "data_freshness": {
      "kvk_data": "2024-09-04",
      "news_data": "2024-09-04"
    }
  }
}
```

**Response - Error (400)**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "kvk_number": ["Must be exactly 8 digits"]
    },
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Response - Error (404)**
```json
{
  "error": {
    "code": "COMPANY_NOT_FOUND", 
    "message": "No company found with the provided KvK number",
    "details": {
      "kvk_number": "12345678"
    },
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Response - Error (429)**
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Rate limit exceeded",
    "details": {
      "limit": 100,
      "window": "1 hour", 
      "retry_after": 3600
    },
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Response - Error (500)**
```json
{
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "An internal error occurred while processing the request",
    "details": {
      "service": "openai_service",
      "error_type": "timeout"
    },
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### 2. Nederlandse Bedrijfsanalyse

#### `POST /nederlands-bedrijf-analyse`

Voert een Nederlandse bedrijfsanalyse uit volgens de nieuwe workflow specificatie met Nederlandse nieuwsbronnen prioriteit.

**Request Body**
```json
{
  "company_name": "ASML Holding N.V.",
  "kvk_nummer": "17014545", 
  "contactpersoon": "Peter Wennink"
}
```

**Response**
```json
{
  "bedrijfsnaam": "ASML Holding N.V.",
  "kvk_nummer": "17014545",
  "contactpersoon": "Peter Wennink",
  "goed_nieuws": [
    {
      "titel": "ASML behaalt recordomzet in Q3 2024",
      "link": "https://fd.nl/bedrijfsleven/1234567/asml-recordomzet",
      "bron": "fd.nl"
    }
  ],
  "slecht_nieuws": [
  ],
  "samenvatting": "Analyse voor ASML Holding N.V.: 3 positieve berichten gevonden, 2 negatieve items gevonden.",
  "analysis_timestamp": "2024-01-15T10:30:00Z",
  "bronnen_gecontroleerd": ["fd.nl", "nrc.nl", "volkskrant.nl", "nos.nl", "bnr.nl"]
}
```

**Belangrijke kenmerken:**
- **Nederlandse bronnen prioriteit** - FD, NRC, Volkskrant, NOS, BNR
- **Contactpersoon integratie** - zoekt naar contactpersoon in alle bronnen
- **90 dagen lookback** - laatste 90 dagen voor nieuws
- **Gestructureerde output** - bullet points met bron en link

### 3. Simple Company Analysis

#### `POST /analyze-company-simple`

Vereenvoudigde bedrijfsanalyse met web search en juridische case lookup.

**Request Body**
```json
{
  "company_name": "ASML Holding N.V."
}
```

**Response**
```json
{
  "bedrijf": "ASML Holding N.V.",
  "samenvatting": "Analysis for ASML Holding N.V.: 5 positive articles found, 3 negative items found.",
  "goed_nieuws": [
    {
      "titel": "ASML reports strong Q3 results",
      "link": "https://example.com/news1",
      "bron": "TechNews"
    }
  ],
  "slecht_nieuws": [
  ]
}
```

### 4. Health Check

#### `GET /health`

Controleert de status van de API en externe dependencies.

**Response - Healthy (200)**
```json
{
  "status": "healthy",
  "timestamp": "2025-09-04T10:30:00.000Z",
  "version": "1.0.0",
  "dependencies": {
    "kvk_api": "healthy",
    "openai_api": "healthy", 
  },
  "performance": {
    "avg_response_time_ms": 1250,
    "success_rate": 0.987
  }
}
```

**Response - Unhealthy (503)**
```json
{
  "status": "unhealthy",
  "timestamp": "2025-09-04T10:30:00.000Z", 
  "version": "1.0.0",
  "dependencies": {
    "kvk_api": "unhealthy",
    "openai_api": "healthy",
  },
  "issues": [
    "KvK API is not responding",
  ]
}
```

### 3. API Status

#### `GET /status`

Geeft uitgebreide API statistieken en metrics.

**Response (200)**
```json
{
  "api_info": {
    "name": "Bedrijfsanalyse API",
    "version": "1.0.0",
    "environment": "production",
    "uptime_seconds": 86400
  },
  "statistics": {
    "requests_today": 1547,
    "successful_requests": 1502,
    "failed_requests": 45,
    "average_response_time_ms": 1250
  },
  "rate_limits": {
    "default_limit": 100,
    "window_seconds": 3600,
    "current_usage": 23
  }
}
```

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Request validation failed |
| `AUTHENTICATION_ERROR` | 401 | Invalid or missing API key |
| `AUTHORIZATION_ERROR` | 403 | API key lacks required permissions |
| `COMPANY_NOT_FOUND` | 404 | KvK number not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `EXTERNAL_API_ERROR` | 502 | External service unavailable |
| `TIMEOUT_ERROR` | 504 | Request timeout |
| `INTERNAL_SERVER_ERROR` | 500 | Server error |

## Rate Limiting

- **Standard Tier**: 100 requests/hour
- **Headers**: 
  - `X-RateLimit-Limit`: Request limit
  - `X-RateLimit-Remaining`: Remaining requests  
  - `X-RateLimit-Reset`: Reset timestamp
- **Behavior**: HTTP 429 when exceeded

## SDKs and Examples

### cURL Example
```bash
curl -X POST "https://api.bedrijfsanalyse.nl/v1/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "kvk_number": "12345678",
    "search_depth": "standard"
  }'
```

### Python Example
```python
import httpx

response = httpx.post(
    "https://api.bedrijfsanalyse.nl/v1/analyze-company",
    json={"kvk_number": "12345678"},
    headers={"X-API-Key": "your-api-key"}
)
data = response.json()
```