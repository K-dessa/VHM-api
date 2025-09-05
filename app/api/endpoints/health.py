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


async def check_kvk_api() -> str:
    """Check KvK API connectivity."""
    if not settings.KVK_API_KEY:
        return "unavailable"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Use a basic test endpoint of KvK API
            response = await client.get(
                "https://api.kvk.nl/api/v1/naamgevingen",
                headers={"apikey": settings.KVK_API_KEY},
                params={"kvkNummer": "27312152"},  # Test with a known valid number
            )
            if response.status_code == 200:
                return "healthy"
            elif response.status_code == 401:
                return "unhealthy"  # Invalid API key
            else:
                return "degraded"
    except Exception as e:
        logger.warning("KvK API health check failed", error=str(e))
        return "unhealthy"


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


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint that verifies connectivity to external dependencies.

    Returns:
    - healthy: All dependencies are working
    - degraded: Some dependencies have issues but core functionality works
    - unhealthy: Critical dependencies are failing
    """
    start_time = time.time()

    # Run all health checks concurrently
    kvk_status, openai_status, rechtspraak_status = await asyncio.gather(
        check_kvk_api(),
        check_openai_api(),
        check_rechtspraak_nl(),
        return_exceptions=True,
    )

    # Convert exceptions to unhealthy status
    if isinstance(kvk_status, Exception):
        kvk_status = "unhealthy"
    if isinstance(openai_status, Exception):
        openai_status = "unhealthy"
    if isinstance(rechtspraak_status, Exception):
        rechtspraak_status = "unhealthy"

    dependencies = {
        "kvk_api": kvk_status,
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


@router.get("/status")
async def status_check():
    """
    Enhanced status endpoint with OpenAI cost monitoring.
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


@router.get("/cost-monitoring")
async def cost_monitoring():
    """
    Detailed OpenAI cost monitoring endpoint.
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
