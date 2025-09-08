import os
import sys
import time
from datetime import datetime, timezone
from typing import Callable

# Set Crawl4AI environment variables BEFORE any imports that might use crawl4ai
os.environ.setdefault('CRAWL4_AI_BASE_DIRECTORY', '/tmp/crawl4ai')
os.environ.setdefault('CRAWL4AI_DB_PATH', '/tmp/crawl4ai/database.db')
os.environ.setdefault('CRAWL4AI_CACHE_DIR', '/tmp/crawl4ai/cache')

# Ensure the directory exists
try:
    os.makedirs(os.environ['CRAWL4_AI_BASE_DIRECTORY'], exist_ok=True)
except Exception:
    # Fallback to /tmp if the preferred directory can't be created
    os.environ['CRAWL4_AI_BASE_DIRECTORY'] = '/tmp/crawl4ai_fallback'
    os.environ['CRAWL4AI_DB_PATH'] = '/tmp/crawl4ai_fallback/database.db'
    os.environ['CRAWL4AI_CACHE_DIR'] = '/tmp/crawl4ai_fallback/cache'
    os.makedirs('/tmp/crawl4ai_fallback', exist_ok=True)

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from .api.endpoints import analyze, health, status, legal
from .api.endpoints.status import MetricsCollector
from .core.config import settings
from .core.exceptions import (BusinessAnalysisError, CompanyNotFoundError,
                              ExternalAPIError, RateLimitError, TimeoutError,
                              ValidationError)
from .core.logging import add_correlation_id, get_correlation_id, get_logger
from .models.response_models import ErrorResponse
from .utils.startup import set_start_time

logger = get_logger(__name__)
set_start_time()

app = FastAPI(
    title="Bedrijfsanalyse API",
    description="""
# Business Analysis API for Dutch Companies

Comprehensive risk assessment and due diligence API for Dutch companies using web crawling, legal databases, and AI-powered analysis.

## Features

* **Web Content Analysis**: AI-ready website crawling with Crawl4AI and Markdown output
* **Legal Risk Assessment**: Comprehensive court case analysis from Rechtspraak.nl
* **News Sentiment Analysis**: AI-powered news analysis focusing on Dutch sources
* **Integrated Risk Scoring**: Multi-factor risk assessment combining all data sources
* **Dutch-focused Analysis**: Prioritizes .nl domains and Dutch news sources
* **Real-time Processing**: Fast parallel data processing with optimized timeouts

## Authentication

All endpoints require authentication via the `X-API-Key` header.

## Rate Limiting

- **Standard Rate Limit**: 100 requests per hour per API key
- **Response Time Targets**: 
  - Standard Analysis: < 30 seconds
  - Dutch Analysis: < 40 seconds  
  - Simple Analysis: < 15 seconds

## Data Sources

1. **Crawl4AI**: Intelligent web crawling with boilerplate removal and content chunking
2. **Rechtspraak.nl**: Dutch legal database (always checked when available)
3. **Dutch News Sources**: FD, NRC, NOS, Volkskrant, BNR and other Dutch media
4. **OpenAI GPT-4**: AI-powered content analysis and risk assessment

## Workflow Improvements

The API now implements an improved workflow without KvK dependencies:
- **Web-first approach**: Crawls company websites for authentic business information
- **Mandatory legal checks**: Always performs Rechtspraak.nl searches when available
- **Dutch content priority**: Focuses on Dutch domains and news sources for local companies
- **Simplified architecture**: Eliminates external API dependencies and costs

## Response Formats

All responses include:
- Request correlation ID for tracking
- Processing time metrics
- Data source information with crawled content
- Quality warnings and analysis limitations

## Error Handling

Comprehensive error responses with:
- Detailed error messages
- Request correlation IDs
- Retry guidance where applicable
- Partial results when possible

## Support

For API support or feature requests, contact the development team.
    """,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    terms_of_service="https://api.bedrijfsanalyse.nl/terms",
    contact={
        "name": "Bedrijfsanalyse API Support",
        "email": "support@bedrijfsanalyse.nl",
        "url": "https://api.bedrijfsanalyse.nl/support"
    },
    license_info={
        "name": "Commercial License",
        "url": "https://api.bedrijfsanalyse.nl/license"
    },
    servers=[
        {
            "url": "https://api.bedrijfsanalyse.nl",
            "description": "Production server"
        },
        {
            "url": "https://staging.api.bedrijfsanalyse.nl", 
            "description": "Staging server"
        }
    ] if not settings.is_development() else [
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        }
    ],
    openapi_tags=[
        {
            "name": "health",
            "description": "Health check and system status endpoints",
            "externalDocs": {
                "description": "Health check documentation",
                "url": "https://api.bedrijfsanalyse.nl/docs#/health"
            }
        },
        {
            "name": "analysis", 
            "description": "Company analysis and risk assessment endpoints - Core business intelligence functionality",
            "externalDocs": {
                "description": "Analysis API documentation", 
                "url": "https://api.bedrijfsanalyse.nl/docs#/analysis"
            }
        },
        {
            "name": "status",
            "description": "System metrics, monitoring endpoints and operational intelligence",
            "externalDocs": {
                "description": "Monitoring and metrics documentation",
                "url": "https://api.bedrijfsanalyse.nl/docs#/status"
            }
        }
    ]
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://api.bedrijfsanalyse.nl", "https://staging.api.bedrijfsanalyse.nl"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
)

# Trusted host middleware for security - temporarily disabled for Railway testing
import os

# Temporarily disable TrustedHostMiddleware for Railway deployment
# if not settings.DEBUG and os.getenv("TESTING") != "true":
#     app.add_middleware(
#         TrustedHostMiddleware, allowed_hosts=["api.bedrijfsanalyse.nl", "localhost", "testserver", "*.railway.app", "*.up.railway.app"]
#     )


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable):
    """Add security headers to responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers[
        "Strict-Transport-Security"
    ] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def logging_middleware(request: Request, call_next: Callable):
    """Add request logging and correlation ID."""
    correlation_id = add_correlation_id()

    start_time = time.time()

    # Log request
    logger.info(
        "Request started",
        method=request.method,
        url=str(request.url),
        user_agent=request.headers.get("user-agent"),
    )

    response = await call_next(request)

    process_time = time.time() - start_time

    # Record metrics
    endpoint = request.url.path
    MetricsCollector.record_request(endpoint, response.status_code, process_time)

    # Log response
    logger.info(
        "Request completed",
        status_code=response.status_code,
        process_time=process_time,
    )

    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Process-Time"] = str(process_time)

    return response


@app.middleware("http")
async def request_size_limit(request: Request, call_next: Callable):
    """Limit request body size to 1MB."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1024 * 1024:  # 1MB
        return JSONResponse(
            status_code=413,
            content=ErrorResponse(
                error="PayloadTooLarge",
                message="Request body too large. Maximum size is 1MB.",
                timestamp=datetime.now(timezone.utc),
            ).dict(),
        )

    return await call_next(request)


# Exception handlers
@app.exception_handler(BusinessAnalysisError)
async def business_analysis_exception_handler(
    request: Request, exc: BusinessAnalysisError
):
    """Handle custom business analysis exceptions."""
    correlation_id = get_correlation_id()

    status_code = 400
    if isinstance(exc, CompanyNotFoundError):
        status_code = 404
    elif isinstance(exc, RateLimitError):
        status_code = 429
    elif isinstance(exc, TimeoutError):
        status_code = 408
    elif isinstance(exc, ExternalAPIError):
        status_code = 502

    logger.error(
        "Business analysis error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        status_code=status_code,
    )

    response_content = ErrorResponse(
        error=type(exc).__name__,
        message=str(exc),
        request_id=correlation_id,
        timestamp=time.time(),
        details={"error_code": getattr(exc, "error_code", None)},
    ).dict()

    # Add retry-after header for rate limit errors
    headers = {}
    if isinstance(exc, RateLimitError) and hasattr(exc, "retry_after"):
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=status_code, content=response_content, headers=headers
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    correlation_id = get_correlation_id()

    logger.warning(
        "Validation error",
        errors=exc.errors(),
    )

    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error="ValidationError",
            message="Request validation failed",
            request_id=correlation_id,
            timestamp=datetime.now(timezone.utc),
            details={"validation_errors": exc.errors()},
        ).model_dump(mode='json'),
    )


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Handle internal server errors."""
    correlation_id = get_correlation_id()

    logger.error(
        "Internal server error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="InternalServerError",
            message="An internal server error occurred",
            request_id=correlation_id,
            timestamp=datetime.now(timezone.utc),
        ).model_dump(mode='json'),
    )


# Include routers
app.include_router(health.router, prefix="", tags=["health"])
app.include_router(analyze.router, prefix="", tags=["analysis"])
app.include_router(status.router, prefix="", tags=["status"])
app.include_router(legal.router, prefix="", tags=["analysis"])  # Legal-only route


@app.on_event("startup")
async def startup_event():
    """Application startup event with endpoint verification."""
    logger.info(
        "Application starting up",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
    )
    
    # Check if all expected endpoints are registered
    expected_endpoints = [
        ("GET", "/health"),
        ("GET", "/status"), 
        ("GET", "/cost-monitoring"),
        ("GET", "/metrics"),
        ("POST", "/analyze-company"),
        ("POST", "/analyze-company-simple"),
        ("POST", "/nederlands-bedrijf-analyse"),
        ("POST", "/LegalSearch")
    ]
    
    registered_routes = []
    missing_endpoints = []
    
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            for method in route.methods:
                if method != "HEAD":  # Skip HEAD methods
                    registered_routes.append((method, route.path))
    
    logger.info("Checking endpoint registration", expected_count=len(expected_endpoints))
    
    for method, path in expected_endpoints:
        if (method, path) in registered_routes:
            logger.info("Endpoint registered", method=method, path=path, status="✓")
        else:
            logger.error("Endpoint missing", method=method, path=path, status="✗")
            missing_endpoints.append(f"{method} {path}")
    
    if missing_endpoints:
        logger.error(
            "Missing endpoints detected", 
            missing_endpoints=missing_endpoints,
            total_missing=len(missing_endpoints)
        )
    else:
        logger.info("All expected endpoints registered successfully")
    
    logger.info(
        "Endpoint registration summary",
        total_registered=len([r for r in registered_routes if r[0] != "HEAD"]),
        expected_endpoints=len(expected_endpoints),
        missing_endpoints=len(missing_endpoints)
    )
    
    # Log all registered routes for debugging
    logger.info("All registered routes:")
    for method, path in sorted(registered_routes):
        logger.info("Route", method=method, path=path)
    
    # Test critical service imports during startup
    try:
        from .services.legal_service import LegalService
        from .services.news_service import NewsService
        from .services.crawl_service import CrawlService
        from .services.risk_service import RiskService
        logger.info("All service imports successful")
        
        # Test service initialization
        try:
            legal_service = LegalService()
            logger.info("LegalService initialized successfully")
        except Exception as e:
            logger.warning("LegalService initialization warning", error=str(e))
            
        try:
            news_service = NewsService()
            logger.info("NewsService initialized successfully")
        except Exception as e:
            logger.warning("NewsService initialization warning", error=str(e))
            
        try:
            crawl_service = CrawlService()
            logger.info("CrawlService initialized successfully")
            await crawl_service.close()  # Clean up immediately
        except Exception as e:
            logger.warning("CrawlService initialization warning", error=str(e))
            
        try:
            risk_service = RiskService()
            logger.info("RiskService initialized successfully")
        except Exception as e:
            logger.warning("RiskService initialization warning", error=str(e))
            
    except ImportError as e:
        logger.error("Critical service import failed", error=str(e))
    except Exception as e:
        logger.error("Service import test failed", error=str(e))
    
    # Container/Production specific diagnostics
    logger.info("Environment diagnostics:")
    logger.info("Python path", python_path=str(sys.path[:3]))  # First 3 paths
    logger.info("Current working directory", cwd=os.getcwd())
    logger.info("Environment variables", debug=settings.DEBUG, app_name=settings.APP_NAME)
    
    # Check if running in container
    if os.path.exists('/.dockerenv'):
        logger.info("Running in Docker container")
    elif os.environ.get('KUBERNETES_SERVICE_HOST'):
        logger.info("Running in Kubernetes")
    else:
        logger.info("Running in standard environment")
    
    # Port and host information
    logger.info("FastAPI app info", 
               version=app.version,
               title=app.title,
               docs_url=app.docs_url,
               total_routes=len(app.routes))
    
    # Final startup validation - make a test request to ourselves if possible
    try:
        import socket
        hostname = socket.gethostname()
        logger.info("Network info", hostname=hostname)
    except Exception as e:
        logger.warning("Could not get network info", error=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Application shutting down")
