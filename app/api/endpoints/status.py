"""
Status and metrics endpoints for monitoring and observability.
"""
import time
try:
    import psutil
except ImportError:
    psutil = None
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
import structlog

from ...core.config import get_settings
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


@router.get(
    "/status",
    summary="Comprehensive API Status Dashboard",
    description="""
    Advanced system status endpoint providing comprehensive API statistics, performance metrics, and service health.
    
    **Comprehensive Metrics Provided:**
    - **Service Information**: Version, uptime, and general status
    - **Request Statistics**: Success rates, error counts, and throughput
    - **Performance Metrics**: Response times, percentiles, and resource usage
    - **External Services**: Health status of dependent services
    - **Cache Performance**: Hit rates and efficiency metrics
    - **Rate Limiting**: Current usage and limits
    
    **Performance Analytics:**
    - Response time percentiles (P50, P90, P95, P99)
    - Memory and CPU usage monitoring
    - Request success/failure rates
    - Service uptime tracking
    
    **Operational Intelligence:**
    - External service health monitoring
    - Cache performance analysis
    - Rate limiting status
    - Resource utilization metrics
    
    **Use Cases:**
    - System monitoring dashboards
    - Performance analysis and optimization
    - Capacity planning
    - Operational health checks
    - SLA monitoring
    """,
    response_description="Comprehensive system status with detailed metrics and health information",
    responses={
        200: {
            "description": "Status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "service": "Bedrijfsanalyse API",
                        "version": "1.0.0",
                        "status": "healthy",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "uptime": {
                            "seconds": 3600,
                            "hours": 1.0,
                            "human_readable": "1h"
                        },
                        "statistics": {
                            "total_requests": 1250,
                            "successful_requests": 1198,
                            "failed_requests": 52,
                            "success_rate_percent": 95.84,
                            "average_response_time_seconds": 2.345
                        },
                        "performance": {
                            "memory_usage_mb": 128.5,
                            "cpu_percent": 12.3,
                            "response_time_percentiles": {
                                "p50": 1.234,
                                "p90": 3.456,
                                "p95": 4.789,
                                "p99": 8.123
                            }
                        },
                        "external_services": {
                            "news_service": {
                                "status": "healthy", 
                                "success_rate_percent": 94.2,
                                "total_calls": 567
                            }
                        },
                        "cache": {
                            "hits": 450,
                            "misses": 123,
                            "hit_rate_percent": 78.5
                        },
                        "rate_limiting": {
                            "active_keys": 25,
                            "requests_per_hour_limit": 100
                        }
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error generating status report"
                    }
                }
            }
        }
    },
    tags=["status"]
)
async def get_status() -> Dict[str, Any]:
    """
    Comprehensive API status endpoint providing detailed system metrics, performance analytics, and service health information.
    
    Returns extensive operational data including request statistics, performance metrics,
    external service health, and resource utilization for system monitoring and optimization.
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
        if psutil is not None:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
        else:
            memory_info = type('obj', (object,), {'rss': 0})()
            cpu_percent = 0.0
        
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


@router.get(
    "/health", 
    summary="Load Balancer Health Check",
    description="""
    Lightweight health check endpoint optimized for load balancers and monitoring systems.
    
    **Fast & Lightweight:**
    - Minimal response time for quick health verification
    - Simple pass/fail health status
    - Optimized for automated monitoring systems
    - No external dependency checks (for speed)
    
    **Use Cases:**
    - Load balancer health checks  
    - Kubernetes liveness/readiness probes
    - Simple uptime monitoring
    - Circuit breaker pattern implementations
    
    **Response Format:**
    Returns basic service identification and timestamp for quick health verification.
    
    **Note:** For comprehensive health checks including external dependencies,
    use the `/health` endpoint in the health router instead.
    """,
    response_description="Simple health status for load balancer checks",
    responses={
        200: {
            "description": "Service is healthy and operational",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2024-01-15T10:30:00Z",
                        "service": "bedrijfsanalyse-api"
                    }
                }
            }
        },
        503: {
            "description": "Service is unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Service unavailable"
                    }
                }
            }
        }
    },
    tags=["status"]
)
async def health_check() -> Dict[str, str]:
    """
    Lightweight health check endpoint for load balancers and monitoring systems.
    
    Provides fast health verification without external dependency checks
    for optimal performance in automated monitoring scenarios.
    """
    try:
        # Perform basic health checks
        settings = get_settings()
        
        # Basic service health check
        health_status = "healthy"
        
        return {
            "status": health_status,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "bedrijfsanalyse-api"
        }
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get(
    "/metrics", 
    response_class=PlainTextResponse,
    summary="Prometheus Metrics Export",
    description="""
    Export system metrics in Prometheus format for monitoring and alerting systems.
    
    **Prometheus Metrics Provided:**
    - **Request Metrics**: Total requests, success/error counts, response times
    - **External API Metrics**: Call counts and success rates per service
    - **Cache Metrics**: Hit/miss ratios and performance data
    - **System Metrics**: Memory usage, CPU utilization, uptime
    - **Performance Histograms**: Response time percentiles and distributions
    
    **Metric Categories:**
    - `http_requests_total`: Total HTTP request counter
    - `http_request_duration_seconds`: Response time histogram with quantiles
    - `external_api_calls_*`: External service call metrics
    - `cache_hits/misses_total`: Cache performance counters
    - `process_*`: System resource utilization metrics
    
    **Integration Support:**
    - Compatible with Prometheus scraping
    - Grafana dashboard integration ready
    - AlertManager rule compatibility
    - Standard Prometheus metric naming conventions
    
    **Use Cases:**
    - Prometheus metric collection
    - Grafana dashboard visualization
    - Automated alerting with AlertManager
    - Performance monitoring and SLA tracking
    - Capacity planning and resource optimization
    """,
    response_description="Prometheus-formatted metrics data",
    responses={
        200: {
            "description": "Metrics exported successfully",
            "content": {
                "text/plain": {
                    "example": """# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total 1250

# HELP http_request_duration_seconds HTTP request latency  
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds{quantile="0.5"} 1.234
http_request_duration_seconds{quantile="0.95"} 4.789

# HELP external_api_calls_total_news Total external API calls to news
# TYPE external_api_calls_total_news counter
external_api_calls_total_news 567"""
                }
            }
        },
        500: {
            "description": "Error generating metrics",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error generating metrics"
                    }
                }
            }
        }
    },
    tags=["status"]
)
async def get_metrics() -> str:
    """
    Export comprehensive system metrics in Prometheus format for monitoring and alerting.
    
    Provides detailed operational metrics including request statistics, external service health,
    cache performance, and system resource utilization in standard Prometheus format.
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
        if psutil is not None:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
        else:
            memory_info = type('obj', (object,), {'rss': 0})()
            cpu_percent = 0.0
        
        metrics_lines.extend([
            "# HELP process_memory_usage_bytes Process memory usage in bytes",
            "# TYPE process_memory_usage_bytes gauge",
            f"process_memory_usage_bytes {memory_info.rss}",
            "",
            "# HELP process_cpu_usage_percent Process CPU usage percentage",
            "# TYPE process_cpu_usage_percent gauge",
            f"process_cpu_usage_percent {cpu_percent}",
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