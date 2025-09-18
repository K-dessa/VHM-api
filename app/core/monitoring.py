"""
Monitoring and observability infrastructure.
"""
import time
import uuid
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from contextvars import ContextVar
from dataclasses import dataclass, asdict
from enum import Enum
import structlog

from .config import get_settings

logger = structlog.get_logger(__name__)

# Context variables for request tracing
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')
request_start_time_var: ContextVar[float] = ContextVar('request_start_time', default=0.0)


class MetricType(str, Enum):
    """Types of metrics we collect."""
    COUNTER = "counter"
    HISTOGRAM = "histogram" 
    GAUGE = "gauge"
    SUMMARY = "summary"


@dataclass
class Metric:
    """Individual metric data point."""
    name: str
    value: float
    metric_type: MetricType
    labels: Dict[str, str]
    timestamp: datetime
    help_text: str = ""


@dataclass
class TracingSpan:
    """Distributed tracing span."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    tags: Dict[str, Any] = None
    logs: List[Dict[str, Any]] = None
    success: bool = True


class MetricsCollector:
    """Enhanced metrics collector with business logic tracking."""
    
    def __init__(self):
        self._metrics: Dict[str, List[Metric]] = {}
        self._custom_metrics: Dict[str, float] = {}
        self._business_metrics = {
            "analysis_requests_total": 0,
            "analysis_requests_success": 0,
            "analysis_requests_failed": 0,
            "kvk_api_calls_total": 0,
            "kvk_api_calls_success": 0,
            "kvk_api_calls_failed": 0,
            "news_analyses_total": 0,
            "news_analyses_success": 0,
            "news_analyses_failed": 0,
            "openai_tokens_consumed": 0,
            "risk_assessments_generated": 0,
            "high_risk_companies_detected": 0,
            "processing_time_total": 0.0,
        }
        self._cost_tracking = {
            "kvk_api_calls_cost": 0.0,
            "openai_tokens_cost": 0.0,
            "total_cost": 0.0
        }
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter metric."""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            labels=labels or {},
            timestamp=datetime.utcnow()
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(metric)
    
    def record_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a histogram value."""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            labels=labels or {},
            timestamp=datetime.utcnow()
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(metric)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge value."""
        metric = Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels or {},
            timestamp=datetime.utcnow()
        )
        
        # For gauges, we only keep the latest value
        self._metrics[name] = [metric]
    
    def record_business_event(self, event: str, success: bool = True, metadata: Dict[str, Any] = None):
        """Record a business logic event."""
        if event == "analysis_request":
            self._business_metrics["analysis_requests_total"] += 1
            if success:
                self._business_metrics["analysis_requests_success"] += 1
            else:
                self._business_metrics["analysis_requests_failed"] += 1
        
        elif event == "kvk_api_call":
            self._business_metrics["kvk_api_calls_total"] += 1
            if success:
                self._business_metrics["kvk_api_calls_success"] += 1
            else:
                self._business_metrics["kvk_api_calls_failed"] += 1
        
        
        elif event == "news_analysis":
            self._business_metrics["news_analyses_total"] += 1
            if success:
                self._business_metrics["news_analyses_success"] += 1
            else:
                self._business_metrics["news_analyses_failed"] += 1
        
        elif event == "risk_assessment":
            self._business_metrics["risk_assessments_generated"] += 1
            if metadata and metadata.get("risk_level") in ["HIGH", "CRITICAL"]:
                self._business_metrics["high_risk_companies_detected"] += 1
        
        elif event == "openai_tokens":
            if metadata and "tokens" in metadata:
                self._business_metrics["openai_tokens_consumed"] += metadata["tokens"]
        
        elif event == "processing_time":
            if metadata and "duration" in metadata:
                self._business_metrics["processing_time_total"] += metadata["duration"]
    
    def track_cost(self, service: str, cost: float):
        """Track cost metrics."""
        if service == "kvk_api":
            self._cost_tracking["kvk_api_calls_cost"] += cost
        elif service == "openai":
            self._cost_tracking["openai_tokens_cost"] += cost
        
        self._cost_tracking["total_cost"] = (
            self._cost_tracking["kvk_api_calls_cost"] + 
            self._cost_tracking["openai_tokens_cost"]
        )
    
    def get_business_metrics(self) -> Dict[str, Any]:
        """Get current business metrics."""
        metrics = dict(self._business_metrics)
        metrics.update(self._cost_tracking)
        
        # Calculate derived metrics
        total_requests = metrics["analysis_requests_total"]
        if total_requests > 0:
            metrics["analysis_success_rate"] = (
                metrics["analysis_requests_success"] / total_requests * 100
            )
            metrics["avg_processing_time"] = (
                metrics["processing_time_total"] / total_requests
            )
        
        total_kvk_calls = metrics["kvk_api_calls_total"]
        if total_kvk_calls > 0:
            metrics["kvk_success_rate"] = (
                metrics["kvk_api_calls_success"] / total_kvk_calls * 100
            )
        
        return metrics


class RequestTracer:
    """Request tracing for distributed observability."""
    
    def __init__(self):
        self._spans: Dict[str, TracingSpan] = {}
    
    def start_span(self, operation_name: str, parent_span_id: Optional[str] = None) -> TracingSpan:
        """Start a new tracing span."""
        span = TracingSpan(
            span_id=str(uuid.uuid4())[:16],
            trace_id=correlation_id_var.get() or str(uuid.uuid4()),
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=time.time(),
            tags={},
            logs=[]
        )
        
        self._spans[span.span_id] = span
        return span
    
    def finish_span(self, span: TracingSpan, success: bool = True):
        """Finish a tracing span."""
        span.end_time = time.time()
        span.duration = span.end_time - span.start_time
        span.success = success
    
    def add_span_tag(self, span: TracingSpan, key: str, value: Any):
        """Add a tag to a span."""
        if span.tags is None:
            span.tags = {}
        span.tags[key] = value
    
    def add_span_log(self, span: TracingSpan, message: str, level: str = "info"):
        """Add a log entry to a span."""
        if span.logs is None:
            span.logs = []
        
        span.logs.append({
            "timestamp": time.time(),
            "level": level,
            "message": message
        })
    
    def get_span_data(self, span_id: str) -> Optional[Dict[str, Any]]:
        """Get span data for export."""
        span = self._spans.get(span_id)
        if not span:
            return None
        
        return asdict(span)
    
    def get_trace_data(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all spans for a trace."""
        spans = [
            asdict(span) for span in self._spans.values() 
            if span.trace_id == trace_id
        ]
        return sorted(spans, key=lambda x: x['start_time'])


class StructuredLogger:
    """Enhanced structured logging with correlation IDs and performance timing."""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
    
    def log_request_start(self, method: str, url: str, user_agent: str = None):
        """Log request start with correlation ID."""
        correlation_id = str(uuid.uuid4())
        correlation_id_var.set(correlation_id)
        request_start_time_var.set(time.time())
        
        self.logger.info(
            "Request started",
            correlation_id=correlation_id,
            method=method,
            url=url,
            user_agent=user_agent,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return correlation_id
    
    def log_request_end(self, status_code: int, error: str = None):
        """Log request completion."""
        correlation_id = correlation_id_var.get()
        start_time = request_start_time_var.get()
        
        if start_time:
            duration = time.time() - start_time
        else:
            duration = 0
        
        log_data = {
            "correlation_id": correlation_id,
            "status_code": status_code,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if error:
            log_data["error"] = error
            self.logger.error("Request completed with error", **log_data)
        else:
            self.logger.info("Request completed", **log_data)
    
    def log_external_api_call(self, service: str, operation: str, duration: float, success: bool, error: str = None):
        """Log external API calls with timing."""
        log_data = {
            "correlation_id": correlation_id_var.get(),
            "service": service,
            "operation": operation,
            "duration": duration,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if error:
            log_data["error"] = error
        
        self.logger.info("External API call", **log_data)
    
    def log_business_event(self, event: str, data: Dict[str, Any] = None):
        """Log business logic events."""
        log_data = {
            "correlation_id": correlation_id_var.get(),
            "event": event,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if data:
            log_data.update(data)
        
        self.logger.info("Business event", **log_data)


class AlertManager:
    """Alert management for threshold breaches."""
    
    def __init__(self):
        self.settings = get_settings()
        self._alert_rules = {
            "response_time_high": {
                "threshold": 45.0,
                "description": "Response time > 45s"
            },
            "error_rate_high": {
                "threshold": 5.0,
                "description": "Error rate > 5%"
            },
            "external_service_failure": {
                "threshold": 3,  # consecutive failures
                "description": "External service consecutive failures"
            },
            "cost_budget_exceeded": {
                "threshold": 100.0,  # daily budget in euros
                "description": "Daily cost budget exceeded"
            },
            "memory_usage_high": {
                "threshold": 512.0,  # MB
                "description": "Memory usage > 512MB"
            }
        }
        self._active_alerts: Dict[str, Dict] = {}
        self._alert_cooldown = 300  # 5 minutes
    
    def check_response_time_threshold(self, response_time: float):
        """Check response time against threshold."""
        threshold = self._alert_rules["response_time_high"]["threshold"]
        
        if response_time > threshold:
            self._trigger_alert(
                "response_time_high",
                f"Response time {response_time:.3f}s exceeds threshold {threshold}s",
                {"response_time": response_time, "threshold": threshold}
            )
    
    def check_error_rate_threshold(self, error_count: int, total_count: int):
        """Check error rate against threshold."""
        if total_count == 0:
            return
            
        error_rate = (error_count / total_count) * 100
        threshold = self._alert_rules["error_rate_high"]["threshold"]
        
        if error_rate > threshold:
            self._trigger_alert(
                "error_rate_high",
                f"Error rate {error_rate:.1f}% exceeds threshold {threshold}%",
                {"error_rate": error_rate, "threshold": threshold}
            )
    
    def check_cost_threshold(self, current_cost: float):
        """Check cost against daily budget."""
        threshold = self._alert_rules["cost_budget_exceeded"]["threshold"]
        
        if current_cost > threshold:
            self._trigger_alert(
                "cost_budget_exceeded",
                f"Daily cost €{current_cost:.2f} exceeds budget €{threshold:.2f}",
                {"current_cost": current_cost, "budget": threshold}
            )
    
    def _trigger_alert(self, alert_type: str, message: str, data: Dict[str, Any]):
        """Trigger an alert."""
        now = time.time()
        
        # Check if alert is in cooldown
        if alert_type in self._active_alerts:
            last_alert = self._active_alerts[alert_type].get("timestamp", 0)
            if now - last_alert < self._alert_cooldown:
                return  # Skip duplicate alert
        
        alert = {
            "type": alert_type,
            "message": message,
            "data": data,
            "timestamp": now,
            "correlation_id": correlation_id_var.get()
        }
        
        self._active_alerts[alert_type] = alert
        
        # Log the alert
        logger.warning(
            "Alert triggered",
            alert_type=alert_type,
            message=message,
            data=data
        )
        
        # In production, this would send to alerting system
        # (Slack, PagerDuty, email, etc.)
        self._send_alert(alert)
    
    def _send_alert(self, alert: Dict[str, Any]):
        """Send alert to external system."""
        # Placeholder for actual alerting integration
        # Could integrate with Slack, email, PagerDuty, etc.
        print(f"🚨 ALERT: {alert['message']}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get currently active alerts."""
        return list(self._active_alerts.values())
    
    def clear_alert(self, alert_type: str):
        """Clear an active alert."""
        if alert_type in self._active_alerts:
            del self._active_alerts[alert_type]


# Global instances
metrics_collector = MetricsCollector()
request_tracer = RequestTracer()
structured_logger = StructuredLogger()
alert_manager = AlertManager()


def get_correlation_id() -> str:
    """Get current correlation ID."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str):
    """Set correlation ID for current context."""
    correlation_id_var.set(correlation_id)


async def monitor_system_health():
    """Background task to monitor system health and trigger alerts."""
    import psutil
    
    while True:
        try:
            # Check memory usage
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > alert_manager._alert_rules["memory_usage_high"]["threshold"]:
                alert_manager._trigger_alert(
                    "memory_usage_high",
                    f"Memory usage {memory_mb:.1f}MB exceeds threshold",
                    {"memory_mb": memory_mb}
                )
            
            # Record system metrics
            metrics_collector.set_gauge("memory_usage_mb", memory_mb)
            metrics_collector.set_gauge("cpu_percent", process.cpu_percent())
            
            # Check business metrics for alerts
            business_metrics = metrics_collector.get_business_metrics()
            
            # Check error rates
            if business_metrics.get("analysis_requests_total", 0) > 10:  # Minimum sample size
                success_rate = business_metrics.get("analysis_success_rate", 100)
                if success_rate < 95:  # Less than 95% success
                    alert_manager.check_error_rate_threshold(
                        business_metrics.get("analysis_requests_failed", 0),
                        business_metrics.get("analysis_requests_total", 1)
                    )
            
            # Check cost thresholds
            total_cost = business_metrics.get("total_cost", 0)
            if total_cost > 0:
                alert_manager.check_cost_threshold(total_cost)
            
            await asyncio.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            logger.error("System health monitoring error", error=str(e))
            await asyncio.sleep(60)  # Wait longer on error