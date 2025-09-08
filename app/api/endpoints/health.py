import asyncio
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException

from ...core.config import settings
from ...core.logging import get_logger
from ...models.response_models import HealthResponse
from ...services.news_service import NewsService

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/",
    summary="API Root",
    description="Root endpoint providing basic API information and available endpoints",
    tags=["health"]
)
async def root():
    """Root endpoint with basic API information."""
    return {
        "message": "Bedrijfsanalyse API",
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "Documentation not available in production",
        "health": "/health",
        "endpoints": {
            "health": "/health",
            "status": "/status", 
            "analyze_company": "/analyze-company",
            "analyze_company_simple": "/analyze-company-simple",
            "nederlands_bedrijf_analyse": "/nederlands-bedrijf-analyse",
            "legal_search": "/LegalSearch"
        }
    }


async def check_openai_api() -> str:
    """Check OpenAI API connectivity."""
    if not settings.OPENAI_API_KEY:
        return "unavailable"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Use OpenAI models endpoint for basic connectivity check
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            if response.status_code == 200:
                return "healthy"
            elif response.status_code == 401:
                return "unhealthy"  # Invalid API key
            else:
                return "degraded"
    except Exception as e:
        logger.warning("OpenAI API health check failed", error=str(e))
        return "unhealthy"


async def check_rechtspraak_nl() -> str:
    """Check rechtspraak.nl connectivity."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Basic HTTP check to rechtspraak.nl
            response = await client.get("https://www.rechtspraak.nl")
            if response.status_code == 200:
                return "healthy"
            else:
                return "degraded"
    except Exception as e:
        logger.warning("Rechtspraak.nl health check failed", error=str(e))
        return "unhealthy"


@router.get(
    "/health", 
    response_model=HealthResponse,
    summary="System Health Check",
    description="""
    Comprehensive health check endpoint that verifies connectivity to all external dependencies.
    
    This endpoint performs health checks on:
    - **OpenAI API**: AI service availability for news analysis
    - **Rechtspraak.nl**: Dutch legal database accessibility
    
    **Health Status Levels:**
    - `healthy`: All dependencies are working normally
    - `degraded`: Some dependencies have issues but core functionality works
    - `unhealthy`: Critical dependencies are failing
    
    **Use Cases:**
    - Load balancer health checks
    - System monitoring and alerting
    - Dependency status verification
    - Service readiness checks
    """,
    response_description="Detailed health status with dependency information and uptime metrics",
    responses={
        200: {
            "description": "Health check completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "version": "1.0.0",
                        "dependencies": {
                            "openai_api": "healthy", 
                            "rechtspraak_nl": "healthy"
                        },
                        "uptime_seconds": 3600
                    }
                }
            }
        },
        503: {
            "description": "Service unavailable - critical dependencies failing",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "dependencies": {
                            "openai_api": "degraded",
                            "rechtspraak_nl": "healthy"
                        }
                    }
                }
            }
        }
    },
    tags=["health"]
)
async def health_check():
    """
    Comprehensive health check endpoint that verifies connectivity to all external dependencies.
    
    Performs concurrent health checks on OpenAI API and Rechtspraak.nl
    to provide detailed service status information.
    """
    start_time = time.time()

    # Run all health checks concurrently
    openai_status, rechtspraak_status = await asyncio.gather(
        check_openai_api(),
        check_rechtspraak_nl(),
        return_exceptions=True,
    )

    # Convert exceptions to unhealthy status
    if isinstance(openai_status, Exception):
        openai_status = "unhealthy"
    if isinstance(rechtspraak_status, Exception):
        rechtspraak_status = "unhealthy"

    dependencies = {
        "openai_api": openai_status,
        "rechtspraak_nl": rechtspraak_status,
    }

    # Determine overall status
    if all(status == "healthy" for status in dependencies.values()):
        overall_status = "healthy"
    elif any(status == "unhealthy" for status in dependencies.values()):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    from ...utils.startup import get_uptime

    health_response = HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=settings.APP_VERSION,
        dependencies=dependencies,
        uptime_seconds=get_uptime(),
    )

    check_time = time.time() - start_time
    logger.info(
        "Health check completed",
        overall_status=overall_status,
        check_time_seconds=check_time,
        dependencies=dependencies,
    )

    return health_response


@router.get(
    "/status",
    summary="Service Status & Cost Monitoring", 
    description="""
    Enhanced status endpoint providing service status and OpenAI cost monitoring.
    
    This endpoint returns:
    - **Service Status**: Current operational status
    - **OpenAI Usage Metrics**: Token usage and cost estimates
    - **Cost Alerts**: Notifications when spending thresholds are exceeded
    - **Version Information**: Current API version
    
    **Cost Monitoring Features:**
    - Daily cost tracking and limits ($10/day default)
    - Monthly cost estimates ($100/month default)
    - Token usage statistics
    - Automated cost alerts
    
    **Use Cases:**
    - Cost monitoring and budget management
    - Usage analytics and optimization
    - Service status verification
    - Operational dashboards
    """,
    response_description="Service status with detailed cost monitoring information",
    responses={
        200: {
            "description": "Status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "version": "1.0.0",
                        "openai_usage": {
                            "total_requests": 150,
                            "total_input_tokens": 25000,
                            "total_output_tokens": 5000,
                            "estimated_cost_usd": 2.45
                        },
                        "cost_alerts": []
                    }
                }
            }
        },
        200: {
            "description": "Status with cost alerts",
            "content": {
                "application/json": {
                    "example": {
                        "status": "warning",
                        "openai_usage": {
                            "estimated_cost_usd": 12.50
                        },
                        "cost_alerts": [
                            "Daily cost limit exceeded: $12.50 > $10.00"
                        ]
                    }
                }
            }
        }
    },
    tags=["health"]
)
async def status_check():
    """
    Enhanced status endpoint with comprehensive OpenAI cost monitoring and alerts.
    
    Provides real-time service status along with detailed cost tracking for OpenAI API usage.
    """
    status_data = {
        "status": "ok",
        "timestamp": datetime.utcnow(),
        "version": settings.APP_VERSION,
    }
    
    # Add OpenAI cost tracking if available
    try:
        news_service = NewsService()
        usage_stats = news_service.get_usage_stats()
        status_data["openai_usage"] = usage_stats
        
        # Add cost alerts if thresholds are exceeded
        daily_cost_limit = 10.0  # $10 per day limit
        monthly_cost_limit = 100.0  # $100 per month limit
        
        alerts = []
        if usage_stats["estimated_cost_usd"] > daily_cost_limit:
            alerts.append(f"Daily cost limit exceeded: ${usage_stats['estimated_cost_usd']:.2f} > ${daily_cost_limit:.2f}")
        
        if len(alerts) > 0:
            status_data["cost_alerts"] = alerts
            status_data["status"] = "warning"
            
    except ValueError:
        # OpenAI service not available
        status_data["openai_usage"] = {"status": "unavailable", "reason": "Missing OpenAI API key"}
    except Exception as e:
        logger.warning("Failed to get OpenAI usage stats", error=str(e))
        status_data["openai_usage"] = {"status": "error", "error": str(e)}
    
    return status_data


@router.get(
    "/cost-monitoring",
    summary="Detailed Cost Analytics",
    description="""
    Advanced OpenAI cost monitoring and analytics endpoint for financial oversight.
    
    **Detailed Metrics Provided:**
    - **Current Session Statistics**: Token usage and costs for current session
    - **Cost Analysis**: Per-request costs and daily/monthly projections  
    - **Efficiency Metrics**: Token efficiency and cache hit rates
    - **Optimization Recommendations**: Automated suggestions for cost reduction
    
    **Financial Insights:**
    - Cost per request calculations
    - Daily and monthly cost projections
    - Efficiency metrics (tokens per request)
    - Cache performance analysis
    
    **Optimization Features:**
    - Automated cost optimization recommendations
    - Token usage efficiency analysis
    - Cache performance suggestions
    - Prompt optimization guidance
    
    **Use Cases:**
    - Financial planning and budgeting
    - Cost optimization analysis
    - Performance monitoring
    - Resource utilization tracking
    """,
    response_description="Comprehensive cost analytics with optimization recommendations",
    responses={
        200: {
            "description": "Cost monitoring data retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "timestamp": "2024-01-15T10:30:00Z",
                        "current_session": {
                            "total_requests": 150,
                            "total_input_tokens": 25000,
                            "total_output_tokens": 5000,
                            "estimated_cost_usd": 2.45
                        },
                        "cost_analysis": {
                            "cost_per_request_usd": 0.0163,
                            "estimated_daily_cost_usd": 3.92,
                            "estimated_monthly_cost_usd": 117.60
                        },
                        "efficiency_metrics": {
                            "avg_input_tokens_per_request": 166.7,
                            "avg_output_tokens_per_request": 33.3,
                            "cache_hit_rate": 0.25
                        },
                        "recommendations": [
                            "Consider optimizing prompts to reduce token usage"
                        ]
                    }
                }
            }
        },
        503: {
            "description": "OpenAI service unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "OpenAI cost monitoring unavailable: Missing OpenAI API key"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to retrieve cost monitoring data"
                    }
                }
            }
        }
    },
    tags=["health"]
)
async def cost_monitoring():
    """
    Advanced OpenAI cost monitoring endpoint providing detailed financial analytics and optimization recommendations.
    
    Analyzes current usage patterns to provide cost projections, efficiency metrics, 
    and automated recommendations for cost optimization.
    """
    try:
        news_service = NewsService()
        usage_stats = news_service.get_usage_stats()
        
        # Calculate cost per request
        cost_per_request = (
            usage_stats["estimated_cost_usd"] / usage_stats["total_requests"] 
            if usage_stats["total_requests"] > 0 else 0
        )
        
        # Estimate daily/monthly costs based on current usage
        requests_per_hour = 10  # Estimate
        daily_estimated_cost = cost_per_request * requests_per_hour * 24
        monthly_estimated_cost = daily_estimated_cost * 30
        
        monitoring_data = {
            "timestamp": datetime.utcnow(),
            "current_session": usage_stats,
            "cost_analysis": {
                "cost_per_request_usd": round(cost_per_request, 4),
                "estimated_daily_cost_usd": round(daily_estimated_cost, 2),
                "estimated_monthly_cost_usd": round(monthly_estimated_cost, 2),
            },
            "efficiency_metrics": {
                "avg_input_tokens_per_request": (
                    usage_stats["total_input_tokens"] / usage_stats["total_requests"] 
                    if usage_stats["total_requests"] > 0 else 0
                ),
                "avg_output_tokens_per_request": (
                    usage_stats["total_output_tokens"] / usage_stats["total_requests"] 
                    if usage_stats["total_requests"] > 0 else 0
                ),
                "cache_hit_rate": (
                    usage_stats["cache_size"] / max(usage_stats["total_requests"], 1)
                )
            },
            "recommendations": []
        }
        
        # Add recommendations based on usage patterns
        if cost_per_request > 0.50:
            monitoring_data["recommendations"].append("Consider optimizing prompts to reduce token usage")
        
        if usage_stats["cache_size"] < usage_stats["total_requests"] * 0.3:
            monitoring_data["recommendations"].append("Consider increasing cache TTL to improve cost efficiency")
        
        if usage_stats["total_input_tokens"] > 50000:
            monitoring_data["recommendations"].append("High input token usage detected - consider prompt optimization")
        
        return monitoring_data
        
    except ValueError:
        raise HTTPException(
            status_code=503, 
            detail="OpenAI cost monitoring unavailable: Missing OpenAI API key"
        )
    except Exception as e:
        logger.error("Failed to get cost monitoring data", error=str(e))
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve cost monitoring data"
        )
