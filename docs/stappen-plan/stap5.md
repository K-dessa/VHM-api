# Stap 5: Integration, Testing & Deployment

## Doel
Finaliseer de complete applicatie met end-to-end testing, performance optimization, monitoring, en deployment gereed maken.

## Voorbereidingen
- Stap 1-4 volledig afgerond
- Alle services (KvK, Legal, News) werkend
- Basis unit tests geschreven

## Prompts voor implementatie

### 5.1 Risk Assessment Integration
**Prompt**: "Implementeer geïntegreerde risk assessment in app/services/risk_service.py:

1. RiskService class met methodes:
   - calculate_overall_risk(company_info, legal_findings, news_analysis) -> RiskAssessment
   - assess_legal_risk(legal_cases) -> str
   - assess_reputation_risk(news_analysis) -> str
   - assess_financial_risk(company_info, news) -> str
   - assess_operational_risk(all_data) -> str

2. Risk scoring algoritme:
   - Weight factors: legal (40%), reputation (30%), financial (20%), operational (10%)
   - Recent data gets higher weight (< 6 maanden: 1.0x, < 1 jaar: 0.8x, > 1 jaar: 0.6x)
   - Combine quantitative scores met qualitative analysis

3. Recommendations engine:
   - Generate actionable recommendations per risk category
   - Prioritize by impact en urgency
   - Include monitoring suggestions
   - Provide mitigation strategies"

### 5.2 Complete endpoint implementation
**Prompt**: "Finaliseer app/api/endpoints/analyze.py voor complete functionaliteit:

1. Full service orchestration:
   - Parallel execution van alle services
   - Progressive response assembly
   - Graceful degradation bij partial failures
   - Timeout management (30s standard, 60s deep)

2. Response assembly:
   - Combine alle service outputs
   - Calculate integrated risk assessment
   - Add processing metadata
   - Include data freshness indicators

3. Error handling improvements:
   - Detailed error categorization
   - Partial success responses
   - Service-specific error messages
   - User-friendly error explanations"

### 5.3 Status en metrics endpoints
**Prompt**: "Implementeer app/api/endpoints/status.py:

1. /status endpoint:
   - API statistics (requests, success rates)
   - Performance metrics (avg response times)
   - Resource usage (memory, CPU)
   - External service health

2. /metrics endpoint (Prometheus format):
   - Request counters per endpoint
   - Response time histograms
   - Error rate metrics
   - External API call metrics
   - Cache hit/miss rates

3. Health check improvements:
   - Deep health checks voor alle services
   - Dependency status monitoring
   - Performance threshold alerts
   - Historical health data"

### 5.4 Comprehensive integration tests
**Prompt**: "Maak integration tests in tests/test_integration/:

1. test_full_analysis_flow.py:
   - End-to-end happy path testing
   - Test met real/mock external APIs
   - Response format validation
   - Performance threshold validation

2. test_error_scenarios.py:
   - Service failure combinations
   - Timeout scenarios
   - Rate limiting behavior
   - Authentication/authorization failures

3. test_data_consistency.py:
   - Cross-service data validation
   - Risk assessment accuracy
   - Response completeness checks
   - Data freshness validation"

### 5.5 Performance testing
**Prompt**: "Implementeer performance tests in tests/test_performance/:

1. Load testing setup:
   - Use pytest-benchmark of locust
   - Test concurrent request handling (10 concurrent)
   - Memory usage monitoring
   - Response time percentiles

2. Stress testing:
   - Rate limit behavior onder load
   - Resource exhaustion scenarios
   - Recovery after overload
   - Database/cache performance

3. Performance benchmarks:
   - Standard search: < 30s target
   - Deep search: < 60s target  
   - Memory usage: < 512MB per instance
   - Throughput: 10 req/min sustained"

### 5.6 Monitoring en observability
**Prompt**: "Implementeer monitoring in app/core/monitoring.py:

1. Structured logging improvements:
   - Request tracing met correlation IDs
   - Performance timing logs
   - External API call logging
   - Error categorization logging

2. Metrics collection:
   - Custom metrics voor business logic
   - External service SLA tracking
   - Cost tracking (OpenAI tokens)
   - User behavior metrics

3. Alerting thresholds:
   - Response time > 45s
   - Error rate > 5%
   - External service failures
   - Cost budget overage"

### 5.7 Configuration management
**Prompt**: "Verbeter configuration in app/core/config.py:

1. Environment-specific configs:
   - Development, testing, production settings
   - External service timeouts per env
   - Logging levels per environment
   - Feature flags voor nieuwe functionality

2. Configuration validation:
   - Required environment variables check
   - Value range validation
   - API key format validation
   - Configuration test suite

3. Runtime configuration:
   - Health check intervals
   - Cache TTL settings
   - Rate limit configurations
   - Search depth parameters"

### 5.8 Security hardening
**Prompt**: "Implementeer security measures:

1. Input validation improvements:
   - Stricter schema validation
   - Input sanitization
   - Size limit enforcement
   - Malicious content detection

2. API security enhancements:
   - API key rotation support
   - Request signing (optional)
   - IP whitelisting capability
   - Audit logging

3. Security headers:
   - HTTPS enforcement
   - Security headers middleware
   - CORS policy refinement
   - Content security policy"

### 5.9 Documentation en OpenAPI
**Prompt**: "Verbeter API documentatie:

1. OpenAPI schema improvements:
   - Detailed descriptions voor alle endpoints
   - Response examples voor success/error cases
   - Authentication documentation
   - Rate limiting documentation

2. Code documentation:
   - Docstrings voor alle public methods
   - Type hints completeness check
   - Architecture documentation
   - Service interaction diagrams

3. User guides:
   - Getting started guide
   - API usage examples
   - Error handling guide
   - Best practices documentation"

### 5.10 Deployment preparation
**Prompt**: "Bereid deployment voor:

1. Dockerfile optimization:
   ```dockerfile
   FROM python:3.11-slim
   
   # Multi-stage build
   # Dependencies installation
   # Security best practices
   # Health check configuration
   # Non-root user setup
   ```

2. Docker-compose voor local development:
   - Redis cache service (optional)
   - Environment variable management
   - Volume mounts voor development
   - Port configuration

3. Production deployment checklist:
   - Environment variables configuration
   - SSL certificate setup
   - Load balancer configuration
   - Monitoring stack integration
   - Backup/disaster recovery plan"

### 5.11 Final testing suite
**Prompt**: "Maak comprehensive test suite:

1. Test configuration:
   - pytest.ini setup
   - Coverage configuration (>90% target)
   - Test markers (unit, integration, performance)
   - CI/CD pipeline configuration

2. Test data management:
   - Shared test fixtures
   - Mock data generators
   - Test database setup
   - External API mocking

3. Quality gates:
   - Code coverage thresholds
   - Performance benchmarks
   - Security scanning
   - Dependency vulnerability checks"

### 5.12 Production readiness checklist
**Prompt**: "Verificeer production readiness:

1. Functional requirements:
   - [ ] Alle API endpoints werkend
   - [ ] Error handling compleet
   - [ ] Authentication/authorization
   - [ ] Rate limiting geïmplementeerd

2. Non-functional requirements:
   - [ ] Performance targets gehaald
   - [ ] Security measures actief
   - [ ] Monitoring en logging
   - [ ] Documentation compleet

3. Operational requirements:
   - [ ] Health checks werkend
   - [ ] Metrics beschikbaar
   - [ ] Deployment scripts
   - [ ] Rollback procedures"

## Verwacht resultaat
- Volledig werkende Bedrijfsanalyse API
- Comprehensive test coverage (>90%)
- Performance binnen specified targets
- Production-ready deployment
- Complete monitoring en observability
- Security hardening implemented
- Documentation compleet

## Verificatie scripts

### Complete API test
```bash
#!/bin/bash
# test_complete_api.sh

echo "Testing complete API functionality..."

# Test health endpoint
echo "1. Health check:"
curl -s http://localhost:8000/health | jq

# Test complete analysis
echo "2. Complete company analysis:"
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "kvk_number": "69599084",
    "search_depth": "deep",
    "date_range": "1y",
    "include_positive": true,
    "include_negative": true,
    "language": "nl"
  }' | jq

# Test error handling
echo "3. Error handling:"
curl -X POST "http://localhost:8000/analyze-company" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"kvk_number": "invalid"}' | jq

# Test rate limiting
echo "4. Rate limiting test:"
for i in {1..105}; do
  curl -s -w "%{http_code}\n" -X POST "http://localhost:8000/analyze-company" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: test-key" \
    -d '{"kvk_number": "12345678"}' > /dev/null
done | tail -5

echo "API test completed!"
```

### Performance test
```bash
#!/bin/bash
# test_performance.sh

echo "Running performance tests..."

# Load testing
echo "1. Load test - 10 concurrent requests:"
ab -n 50 -c 10 -T application/json -H "X-API-Key: test-key" \
  -p test_payload.json http://localhost:8000/analyze-company

# Memory usage monitoring
echo "2. Memory usage test:"
python tests/test_performance/memory_test.py

# Response time percentiles
echo "3. Response time analysis:"
python tests/test_performance/timing_test.py

echo "Performance test completed!"
```

## Final deployment steps
1. **Environment setup**: Configure alle environment variables
2. **SSL certificates**: Setup HTTPS certificates
3. **Load balancer**: Configure reverse proxy/load balancer
4. **Monitoring**: Deploy monitoring stack (Prometheus/Grafana)
5. **Alerts**: Configure alerting rules
6. **Backup**: Setup backup procedures
7. **Documentation**: Deploy API documentation
8. **Go-live**: Perform final smoke tests

## Success criteria
- ✅ API response times within SLA (< 30s standard, < 60s deep)
- ✅ Error rate < 1% under normal load
- ✅ Memory usage < 512MB per instance
- ✅ Test coverage > 90%
- ✅ Security scan passed
- ✅ Documentation complete en up-to-date
- ✅ Monitoring en alerting operational
- ✅ Disaster recovery tested

## Post-deployment monitoring
- Monitor API performance metrics
- Track error rates en patterns
- Monitor external service dependencies
- Track cost metrics (OpenAI usage)
- User feedback collection
- Performance optimization opportunities

Dit completteert het volledige stappenplan voor de Bedrijfsanalyse API implementatie!