"""
Status and metrics endpoints for monitoring and observability.
"""
import time
import psutil
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
import structlog

from ...core.config import get_settings
from ...services.kvk_service import KvKService
from ...services.legal_service import LegalService
from ...services.news_service import NewsService
from ...utils.rate_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)

router = APIRouter()

# Global metrics storage (in production, use Redis or similar)
_metrics = {
    "requests_total": 0,
    "requests_success": 0,
    "requests_error": 0,
    "response_times": [],
    "external_api_calls": {
        "kvk": {"total": 0, "success": 0, "error": 0},
        "legal": {"total": 0, "success": 0, "error": 0},
        "news": {"total": 0, "success": 0, "error": 0}
    },
    "cache_hits": 0,
    "cache_misses": 0,
    "start_time": datetime.utcnow()
}


class MetricsCollector:
    """Utility class for collecting application metrics."""
    
    @staticmethod
    def record_request(endpoint: str, status_code: int, response_time: float):
        """Record a request metric."""
        _metrics["requests_total"] += 1
        
        if 200 <= status_code < 300:
            _metrics["requests_success"] += 1
        else:
            _metrics["requests_error"] += 1
        
        _metrics["response_times"].append({
            "endpoint": endpoint,
            "response_time": response_time,
            "timestamp": datetime.utcnow()
        })
        
        # Keep only last 1000 response times
        if len(_metrics["response_times"]) > 1000:
            _metrics["response_times"] = _metrics["response_times"][-1000:]
    
    @staticmethod
    def record_external_api_call(service: str, success: bool):
        """Record an external API call."""
        if service in _metrics["external_api_calls"]:
            _metrics["external_api_calls"][service]["total"] += 1
            if success:
                _metrics["external_api_calls"][service]["success"] += 1
            else:
                _metrics["external_api_calls"][service]["error"] += 1
    
    @staticmethod
    def record_cache_event(hit: bool):
        """Record a cache hit/miss."""
        if hit:
            _metrics["cache_hits"] += 1
        else:
            _metrics["cache_misses"] += 1


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    Get comprehensive API status information.
    
    Returns:
        Dict containing API statistics, performance metrics, and service health
    """
    try:
        # Calculate uptime
        uptime_seconds = (datetime.utcnow() - _metrics["start_time"]).total_seconds()
        uptime_hours = uptime_seconds / 3600
        
        # Calculate success rate
        total_requests = _metrics["requests_total"]
        success_rate = (
            _metrics["requests_success"] / total_requests * 100 
            if total_requests > 0 else 100.0
        )
        
        # Calculate average response time
        recent_response_times = [
            rt["response_time"] for rt in _metrics["response_times"][-100:]
        ]
        avg_response_time = (
            sum(recent_response_times) / len(recent_response_times)
            if recent_response_times else 0.0
        )
        
        # Get system resource usage
        process = psutil.Process()
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent()
        
        # Rate limiter status
        rate_limiter = get_rate_limiter()
        
        # External service health
        external_services = await _check_external_services()
        
        status_data = {
            "service": "Bedrijfsanalyse API",
            "version": "1.0.0",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": {
                "seconds": int(uptime_seconds),
                "hours": round(uptime_hours, 2),
                "human_readable": _format_uptime(uptime_seconds)
            },
            "statistics": {
                "total_requests": total_requests,
                "successful_requests": _metrics["requests_success"],
                "failed_requests": _metrics["requests_error"],
                "success_rate_percent": round(success_rate, 2),
                "average_response_time_seconds": round(avg_response_time, 3)
            },
            "performance": {
                "memory_usage_mb": round(memory_info.rss / 1024 / 1024, 2),
                "cpu_percent": cpu_percent,
                "response_time_percentiles": _calculate_response_time_percentiles()
            },
            "external_services": external_services,
            "cache": {
                "hits": _metrics["cache_hits"],
                "misses": _metrics["cache_misses"],
                "hit_rate_percent": (
                    _metrics["cache_hits"] / (_metrics["cache_hits"] + _metrics["cache_misses"]) * 100
                    if (_metrics["cache_hits"] + _metrics["cache_misses"]) > 0 else 0.0
                )
            },
            "rate_limiting": {
                "active_keys": len(rate_limiter._requests) if hasattr(rate_limiter, '_requests') else 0,
                "requests_per_hour_limit": rate_limiter.max_requests if hasattr(rate_limiter, 'max_requests') else 100
            }
        }
        
        return status_data
        
    except Exception as e:
        logger.error("Error generating status report", error=str(e))
        raise HTTPException(status_code=500, detail="Error generating status report")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Simple health check endpoint for load balancers.
    
    Returns:
        Simple health status
    """
    try:
        # Perform basic health checks
        settings = get_settings()
        
        # Check if we can create services (basic dependency check)
        try:
            kvk_service = KvKService()
            health_status = "healthy"
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            health_status = "degraded"
        
        return {
            "status": health_status,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "bedrijfsanalyse-api"
        }
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> str:
    """
    Get metrics in Prometheus format for monitoring.
    
    Returns:
        Prometheus-formatted metrics
    """
    try:
        metrics_lines = []
        
        # Request metrics
        metrics_lines.extend([
            "# HELP http_requests_total Total number of HTTP requests",
            "# TYPE http_requests_total counter",
            f"http_requests_total {_metrics['requests_total']}",
            "",
            "# HELP http_requests_success_total Total number of successful HTTP requests",
            "# TYPE http_requests_success_total counter", 
            f"http_requests_success_total {_metrics['requests_success']}",
            "",
            "# HELP http_requests_error_total Total number of failed HTTP requests",
            "# TYPE http_requests_error_total counter",
            f"http_requests_error_total {_metrics['requests_error']}",
            ""
        ])
        
        # Response time histogram
        percentiles = _calculate_response_time_percentiles()
        metrics_lines.extend([
            "# HELP http_request_duration_seconds HTTP request latency",
            "# TYPE http_request_duration_seconds histogram",
            f"http_request_duration_seconds{{quantile=\"0.5\"}} {percentiles.get('p50', 0)}",
            f"http_request_duration_seconds{{quantile=\"0.95\"}} {percentiles.get('p95', 0)}",
            f"http_request_duration_seconds{{quantile=\"0.99\"}} {percentiles.get('p99', 0)}",
            ""
        ])
        
        # External API metrics
        for service, stats in _metrics["external_api_calls"].items():
            metrics_lines.extend([
                f"# HELP external_api_calls_total_{service} Total external API calls to {service}",
                f"# TYPE external_api_calls_total_{service} counter",
                f"external_api_calls_total_{service} {stats['total']}",
                "",
                f"# HELP external_api_calls_success_{service} Successful external API calls to {service}",
                f"# TYPE external_api_calls_success_{service} counter", 
                f"external_api_calls_success_{service} {stats['success']}",
                "",
                f"# HELP external_api_calls_error_{service} Failed external API calls to {service}",
                f"# TYPE external_api_calls_error_{service} counter",
                f"external_api_calls_error_{service} {stats['error']}",
                ""
            ])
        
        # Cache metrics
        metrics_lines.extend([
            "# HELP cache_hits_total Total cache hits",
            "# TYPE cache_hits_total counter",
            f"cache_hits_total {_metrics['cache_hits']}",
            "",
            "# HELP cache_misses_total Total cache misses", 
            "# TYPE cache_misses_total counter",
            f"cache_misses_total {_metrics['cache_misses']}",
            ""
        ])
        
        # System metrics
        process = psutil.Process()
        memory_info = process.memory_info()
        
        metrics_lines.extend([
            "# HELP process_memory_usage_bytes Process memory usage in bytes",
            "# TYPE process_memory_usage_bytes gauge",
            f"process_memory_usage_bytes {memory_info.rss}",
            "",
            "# HELP process_cpu_usage_percent Process CPU usage percentage",
            "# TYPE process_cpu_usage_percent gauge",
            f"process_cpu_usage_percent {process.cpu_percent()}",
            ""
        ])
        
        # Uptime
        uptime_seconds = (datetime.utcnow() - _metrics["start_time"]).total_seconds()
        metrics_lines.extend([
            "# HELP process_uptime_seconds Process uptime in seconds", 
            "# TYPE process_uptime_seconds counter",
            f"process_uptime_seconds {int(uptime_seconds)}",
            ""
        ])
        
        return "\n".join(metrics_lines)
        
    except Exception as e:
        logger.error("Error generating metrics", error=str(e))
        raise HTTPException(status_code=500, detail="Error generating metrics")


async def _check_external_services() -> Dict[str, Dict[str, Any]]:
    """Check the health of external services."""
    services = {}
    
    # KvK API health check
    try:
        kvk_service = KvKService()
        # Try a simple health check (this might need to be implemented in KvKService)
        kvk_stats = _metrics["external_api_calls"]["kvk"]
        success_rate = (
            kvk_stats["success"] / kvk_stats["total"] * 100 
            if kvk_stats["total"] > 0 else 100.0
        )
        
        services["kvk_api"] = {
            "status": "healthy" if success_rate > 80 else "degraded",
            "success_rate_percent": round(success_rate, 2),
            "total_calls": kvk_stats["total"],
            "last_check": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        services["kvk_api"] = {
            "status": "unavailable", 
            "error": str(e),
            "last_check": datetime.utcnow().isoformat()
        }
    
    # Legal service health check
    try:
        legal_service = LegalService()
        await legal_service.initialize()
        
        legal_stats = _metrics["external_api_calls"]["legal"]
        success_rate = (
            legal_stats["success"] / legal_stats["total"] * 100 
            if legal_stats["total"] > 0 else 100.0
        )
        
        services["legal_service"] = {
            "status": "healthy" if legal_service.robots_allowed else "restricted",
            "success_rate_percent": round(success_rate, 2),
            "robots_allowed": legal_service.robots_allowed,
            "total_calls": legal_stats["total"],
            "last_check": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        services["legal_service"] = {
            "status": "unavailable",
            "error": str(e),
            "last_check": datetime.utcnow().isoformat()
        }
    
    # News service health check
    try:
        news_service = NewsService()
        news_stats = _metrics["external_api_calls"]["news"]
        success_rate = (
            news_stats["success"] / news_stats["total"] * 100 
            if news_stats["total"] > 0 else 100.0
        )
        
        services["news_service"] = {
            "status": "healthy" if success_rate > 80 else "degraded",
            "success_rate_percent": round(success_rate, 2),
            "total_calls": news_stats["total"],
            "last_check": datetime.utcnow().isoformat()
        }
        
    except ValueError:
        services["news_service"] = {
            "status": "unavailable",
            "error": "OpenAI API key not configured",
            "last_check": datetime.utcnow().isoformat()
        }
    except Exception as e:
        services["news_service"] = {
            "status": "unavailable",
            "error": str(e),
            "last_check": datetime.utcnow().isoformat()
        }
    
    return services


def _calculate_response_time_percentiles() -> Dict[str, float]:
    """Calculate response time percentiles."""
    if not _metrics["response_times"]:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
    
    # Get recent response times (last 1000)
    times = sorted([rt["response_time"] for rt in _metrics["response_times"][-1000:]])
    
    def percentile(data, p):
        k = (len(data) - 1) * p
        f = int(k)
        c = k - f
        if f == len(data) - 1:
            return data[f]
        return data[f] * (1 - c) + data[f + 1] * c
    
    return {
        "p50": round(percentile(times, 0.5), 3),
        "p90": round(percentile(times, 0.9), 3),
        "p95": round(percentile(times, 0.95), 3),
        "p99": round(percentile(times, 0.99), 3)
    }


def _format_uptime(seconds: float) -> str:
    """Format uptime in human-readable format."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    
    if not parts:
        return f"{int(seconds)}s"
    
    return " ".join(parts)


# Make metrics collector available for import
__all__ = ["MetricsCollector"]