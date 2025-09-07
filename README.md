# Bedrijfsanalyse API

Comprehensive risk assessment and due diligence API for Dutch companies. Works with **company names** (KvK numbers optional) and integrates legal sources with AI-powered analysis to provide actionable business intelligence.

## 🚀 Features

- **Name-Based Analysis**: Company analysis based on business name (KvK optional)
- **Mandatory Legal Checks**: Always performs Rechtspraak.nl legal database search
- **Dutch-Focused News**: Prioritizes Dutch news sources (FD, NRC, Volkskrant, NOS, BNR)
- **Contact Person Integration**: Includes contact persons in search queries
- **AI-Powered Analysis**: OpenAI GPT-4 powered sentiment analysis
- **Multiple Workflow Options**: Standard, Dutch-focused, and simple analysis endpoints
- **Real-time Processing**: Parallel data processing with 30-90s response times
- **Comprehensive Monitoring**: Prometheus metrics, health checks, and alerting
- **Production Ready**: Docker deployment with security hardening

## 📋 Requirements

- Python 3.11+
- Docker & Docker Compose
- KvK API Access Key
- OpenAI API Key (for news analysis)
- Google Custom Search API Key + Engine ID (for extra web links)

## 🛠 Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd FastAPIProject
```

### 2. Environment Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Configure required variables in `.env`:

```env
# Application
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# External API Keys
KVK_API_KEY=your_kvk_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_SEARCH_API_KEY=your_google_search_api_key
GOOGLE_SEARCH_ENGINE_ID=your_cse_engine_id

# Authentication
API_KEYS=your-secure-api-key-32-chars-min,another-key-if-needed

# Performance Tuning
RATE_LIMIT_REQUESTS=100
KVK_TIMEOUT=10
OPENAI_TIMEOUT=30
```

### 3. Development Setup

#### Option A: Docker (Recommended)

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f bedrijfsanalyse-api
```

#### Option B: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start development server
uvicorn app.main:app --reload --port 8000
```

## 📖 API Usage

### Authentication

All requests require authentication via the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/health
```

### Basic Company Analysis (Name-Based)

```bash
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "company_name": "ASML Holding N.V.",
    "kvk_nummer": "17014545",
    "contactpersoon": "Peter Wennink",
    "search_depth": "standard",
    "news_date_range": "last_year",
    "legal_date_range": "last_3_years"
  }'
```

### Nederlandse Bedrijfsanalyse (Recommended)

```bash
curl -X POST "http://localhost:8000/nederlands-bedrijf-analyse" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "company_name": "ASML Holding N.V.",
    "kvk_nummer": "17014545",
    "contactpersoon": "Peter Wennink"
  }'
```

### Simple Analysis

```bash
curl -X POST "http://localhost:8000/analyze-company-simple" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "company_name": "ASML Holding N.V."
  }'
```

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and system status |
| `/status` | GET | Detailed system metrics and statistics |
| `/metrics` | GET | Prometheus metrics |
| `/analyze-company` | POST | Name-based company analysis (KvK optional) |
| `/nederlands-bedrijf-analyse` | POST | Dutch-focused analysis with mandatory legal check |
| `/analyze-company-simple` | POST | Simplified analysis with structured output |
| `/docs` | GET | Interactive API documentation |

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Application environment |
| `DEBUG` | `false` | Debug mode |
| `KVK_API_KEY` | - | Dutch Chamber of Commerce API key |
| `OPENAI_API_KEY` | - | OpenAI API key for news analysis |
| `API_KEYS` | - | Comma-separated list of valid API keys |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per hour per API key |
| `ANALYSIS_TIMEOUT_STANDARD` | `30` | Timeout for standard analysis (seconds) |
| `ANALYSIS_TIMEOUT_DEEP` | `60` | Timeout for deep analysis (seconds) |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_LEGAL_SERVICE` | `true` | Enable legal case analysis |
| `ENABLE_NEWS_SERVICE` | `true` | Enable news sentiment analysis |
| `ENABLE_METRICS_COLLECTION` | `true` | Enable Prometheus metrics |
| `ENABLE_ALERTING` | `true` | Enable alert notifications |

## 🧪 Testing

### Run Complete Test Suite

```bash
# Make sure API is running, then:
./scripts/test_complete_api.sh
```

### Unit Tests

```bash
pytest tests/ -v
```

### Performance Tests

```bash
python tests/test_performance/test_memory_test.py
python tests/test_performance/test_timing_test.py
```

### Integration Tests

```bash
pytest tests/test_integration/ -v
```

## 🚀 Deployment

### Production Deployment

1. **Configure Production Environment**:
   ```bash
   # Update .env for production
   ENVIRONMENT=production
   DEBUG=false
   LOG_LEVEL=WARNING
   SECRET_KEY=your-secret-key
   ```

2. **Run Deployment Script**:
   ```bash
   ./scripts/deploy.sh
   ```

3. **Verify Deployment**:
   ```bash
   curl -f http://localhost:8000/health
   ```

### Docker Production Setup

```bash
# Build production image
docker build -t bedrijfsanalyse-api:latest .

# Run with production settings
docker run -d \
  --name bedrijfsanalyse-api \
  --env-file .env \
  -p 8000:8000 \
  bedrijfsanalyse-api:latest
```

## 📈 Monitoring

### Health Checks

```bash
# Basic health
curl http://localhost:8000/health

# Detailed status
curl http://localhost:8000/status
```

### Metrics

Prometheus metrics available at `/metrics`:

```bash
curl http://localhost:8000/metrics
```

Key metrics:
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `external_api_calls_total_*` - External API calls
- `process_memory_usage_bytes` - Memory usage

### Logs

```bash
# Docker logs
docker-compose logs -f bedrijfsanalyse-api

# Structured JSON logs with correlation IDs
tail -f logs/app.log | jq '.'
```

## 🔒 Security

### API Key Management

- API keys must be minimum 32 characters
- Store keys securely (environment variables, secrets management)
- Rotate keys regularly
- Monitor key usage via metrics

### Rate Limiting

- Default: 100 requests/hour per API key
- Configurable per environment
- Automatic IP blocking for abuse

### Input Validation

- All inputs sanitized against XSS, SQL injection
- KvK number format validation
- Request size limits (1MB max)

## 🐛 Troubleshooting

### Common Issues

1. **Connection Refused**
   ```bash
   # Check if service is running
   docker-compose ps
   
   # Check logs
   docker-compose logs bedrijfsanalyse-api
   ```

2. **API Key Issues**
   ```bash
   # Verify API key in environment
   echo $API_KEYS
   
   # Test with curl
   curl -H "X-API-Key: your-key" http://localhost:8000/health
   ```

3. **External API Errors**
   ```bash
   # Check KvK API key
   curl -H "apikey: $KVK_API_KEY" https://api.kvk.nl/api/v1/nhr-opendata/v1/basisprofielen/69599084
   
   # Check OpenAI key
   curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
   ```

4. **Performance Issues**
   ```bash
   # Check memory usage
   docker stats bedrijfsanalyse-api
   
   # Run performance tests
   python tests/test_performance/test_memory_test.py
   ```

### Log Analysis

```bash
# Search for errors
docker-compose logs bedrijfsanalyse-api | grep ERROR

# Monitor specific correlation ID
docker-compose logs bedrijfsanalyse-api | grep "correlation_id=YOUR_ID"

# Check external API failures
docker-compose logs bedrijfsanalyse-api | grep "External API call.*success.*false"
```

## 📚 Development

### Project Structure

```
FastAPIProject/
├── app/
│   ├── main.py                 # FastAPI application with 3 analysis endpoints
│   ├── core/                   # Core functionality
│   │   ├── config.py          # Configuration management
│   │   ├── security.py        # Security hardening
│   │   ├── monitoring.py      # Observability
│   │   └── exceptions.py      # Custom exceptions
│   ├── api/                   # API endpoints
│   │   └── endpoints/         # Route handlers
│   │       └── analyze.py     # Main analysis endpoints
│   ├── services/              # Business logic
│   │   ├── kvk_service.py     # KvK integration (optional, with mock fallback)
│   │   ├── legal_service.py   # Legal analysis (MANDATORY Rechtspraak.nl)
│   │   ├── news_service.py    # News analysis (Dutch sources priority)
│   │   └── risk_service.py    # Risk assessment
│   ├── models/                # Pydantic models
│   │   ├── request_models.py  # CompanyAnalysisRequest with contactpersoon
│   │   └── response_models.py # Multiple response formats
│   └── utils/                 # Utilities
├── tests/                     # Test suites
├── scripts/                   # Deployment scripts
└── docs/                      # Updated documentation
```

### Current Workflow Summary

The system now operates with **three main analysis workflows**:

1. **`/analyze-company`**: Standard name-based analysis with optional KvK lookup
2. **`/nederlands-bedrijf-analyse`**: Dutch-focused analysis with mandatory legal checks 
3. **`/analyze-company-simple`**: Simplified output format

**Key Changes from Original Design:**
- **Company name** is now primary input (KvK number optional)
- **Contactpersoon integration** throughout all searches  
- **Mandatory Rechtspraak.nl** checks (always performed)
- **Dutch news source prioritization** (FD, NRC, Volkskrant, etc.)
- **90-day lookback** for news analysis
- **Structured bullet-point output** with source attribution

### Adding New Features

1. **Create Feature Branch**:
   ```bash
   git checkout -b feature/new-analysis-type
   ```

2. **Add Service**:
   ```python
   # app/services/new_service.py
   class NewService:
       async def analyze(self, data):
           # Implementation
           pass
   ```

3. **Add Tests**:
   ```python
   # tests/test_services/test_new_service.py
   def test_new_service():
       # Test implementation
       pass
   ```

4. **Update Documentation**:
   - Update API docs in endpoint decorators
   - Add configuration options
   - Update README if needed

## 📄 License

Commercial License - See [LICENSE](LICENSE) file for details.

## 🤝 Support

- **Issues**: Report bugs and feature requests via GitHub Issues
- **Email**: support@bedrijfsanalyse.nl
- **Documentation**: Full API docs at `/docs` endpoint

---

Built with ❤️ using FastAPI, Python 3.11, and modern DevOps practices.
