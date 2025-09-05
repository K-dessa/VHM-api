"""
Security hardening and protection measures.
"""
import re
import hmac
import hashlib
import secrets
import time
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network, AddressValueError

import structlog
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from .config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class SecurityEvent:
    """Security event for audit logging."""
    event_type: str
    source_ip: str
    user_agent: str
    api_key_prefix: str
    timestamp: datetime
    details: Dict[str, Any]
    severity: str = "INFO"  # INFO, WARNING, CRITICAL


class InputSanitizer:
    """Input validation and sanitization."""
    
    # Dangerous patterns that should be blocked
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript URLs
        r'data:text/html',  # Data URLs with HTML
        r'vbscript:',  # VBScript
        r'on\w+\s*=',  # Event handlers
        r'expression\s*\(',  # CSS expressions
        r'\.\./.*\.\.',  # Directory traversal
        r'union\s+select',  # SQL injection
        r'drop\s+table',  # SQL injection
        r'exec\s*\(',  # Command injection
        r'system\s*\(',  # Command injection
        r'eval\s*\(',  # Code evaluation
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\b)",
        r"(\b(or|and)\s+[\w\s]*=[\w\s]*)",
        r"(['\"][\s]*;[\s]*--)",
        r"(\/\*.*\*\/)",
        r"(\bxp_cmdshell\b)",
    ]
    
    # XSS patterns
    XSS_PATTERNS = [
        r"(<script[^>]*>.*?</script>)",
        r"(<iframe[^>]*>.*?</iframe>)",
        r"(<object[^>]*>.*?</object>)",
        r"(<embed[^>]*>)",
        r"(<link[^>]*>)",
        r"(<meta[^>]*>)",
        r"(javascript\s*:)",
        r"(vbscript\s*:)",
        r"(data\s*:\s*text/html)",
    ]
    
    @classmethod
    def is_safe_string(cls, value: str, max_length: int = 1000) -> bool:
        """Check if string is safe from common attacks."""
        if not isinstance(value, str):
            return False
        
        if len(value) > max_length:
            return False
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning("Dangerous pattern detected", pattern=pattern, value=value[:100])
                return False
        
        return True
    
    @classmethod
    def check_sql_injection(cls, value: str) -> bool:
        """Check for SQL injection patterns."""
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning("SQL injection pattern detected", pattern=pattern, value=value[:100])
                return True
        return False
    
    @classmethod
    def check_xss(cls, value: str) -> bool:
        """Check for XSS patterns."""
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning("XSS pattern detected", pattern=pattern, value=value[:100])
                return True
        return False
    
    @classmethod
    def sanitize_kvk_number(cls, kvk_number: str) -> str:
        """Sanitize and validate KvK number."""
        if not isinstance(kvk_number, str):
            raise ValueError("KvK number must be a string")
        
        # Remove non-numeric characters
        sanitized = re.sub(r'[^0-9]', '', kvk_number)
        
        # Validate length (Dutch KvK numbers are 8 digits)
        if len(sanitized) != 8:
            raise ValueError("KvK number must be exactly 8 digits")
        
        # Validate that it's not all zeros or other invalid patterns
        if sanitized == '00000000' or len(set(sanitized)) == 1:
            raise ValueError("Invalid KvK number pattern")
        
        return sanitized
    
    @classmethod
    def sanitize_search_query(cls, query: str, max_length: int = 200) -> str:
        """Sanitize search query input."""
        if not isinstance(query, str):
            raise ValueError("Search query must be a string")
        
        # Check length
        if len(query) > max_length:
            raise ValueError(f"Search query too long (max {max_length} characters)")
        
        # Check for dangerous patterns
        if not cls.is_safe_string(query, max_length):
            raise ValueError("Search query contains potentially dangerous content")
        
        # Remove excessive whitespace
        sanitized = re.sub(r'\s+', ' ', query.strip())
        
        return sanitized


class IPWhitelist:
    """IP address whitelisting and validation."""
    
    def __init__(self):
        self.settings = get_settings()
        self.allowed_networks: Set[str] = set()
        self.blocked_ips: Set[str] = set()
        self.load_ip_rules()
    
    def load_ip_rules(self):
        """Load IP whitelist/blacklist rules."""
        # Default allowed networks (can be configured via environment)
        default_allowed = [
            "127.0.0.0/8",      # Localhost
            "10.0.0.0/8",       # Private network
            "172.16.0.0/12",    # Private network  
            "192.168.0.0/16",   # Private network
        ]
        
        # In production, this would be loaded from configuration
        for network in default_allowed:
            self.allowed_networks.add(network)
    
    def is_ip_allowed(self, ip_str: str) -> bool:
        """Check if IP address is allowed."""
        try:
            client_ip = ip_address(ip_str)
            
            # Check if IP is explicitly blocked
            if ip_str in self.blocked_ips:
                return False
            
            # In development, allow all
            if self.settings.is_development():
                return True
            
            # Check against allowed networks
            for network_str in self.allowed_networks:
                network = ip_network(network_str)
                if client_ip in network:
                    return True
            
            return False
            
        except AddressValueError:
            logger.warning("Invalid IP address format", ip=ip_str)
            return False
    
    def add_blocked_ip(self, ip_str: str, reason: str = "Manual block"):
        """Add IP to blocklist."""
        self.blocked_ips.add(ip_str)
        logger.warning("IP address blocked", ip=ip_str, reason=reason)


class RequestSigner:
    """Request signing and verification for enhanced security."""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode('utf-8')
    
    def sign_request(self, method: str, path: str, body: str, timestamp: str) -> str:
        """Generate request signature."""
        message = f"{method}|{path}|{body}|{timestamp}"
        signature = hmac.new(
            self.secret_key,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def verify_signature(
        self, 
        method: str, 
        path: str, 
        body: str, 
        timestamp: str, 
        signature: str,
        tolerance: int = 300  # 5 minutes
    ) -> bool:
        """Verify request signature."""
        try:
            # Check timestamp tolerance
            request_time = int(timestamp)
            current_time = int(time.time())
            
            if abs(current_time - request_time) > tolerance:
                logger.warning("Request timestamp outside tolerance", 
                             timestamp=timestamp, current=current_time)
                return False
            
            # Calculate expected signature
            expected_signature = self.sign_request(method, path, body, timestamp)
            
            # Constant-time comparison
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error("Signature verification error", error=str(e))
            return False


class SecurityAuditor:
    """Security event auditing and monitoring."""
    
    def __init__(self):
        self.security_events: List[SecurityEvent] = []
        self.failed_attempts: Dict[str, List[datetime]] = {}
        self.blocked_ips: Dict[str, datetime] = {}
        
        # Thresholds for automatic blocking
        self.max_failed_attempts = 10
        self.attempt_window_minutes = 15
        self.block_duration_hours = 1
    
    def log_security_event(
        self,
        event_type: str,
        request: Request,
        api_key_prefix: str = "",
        details: Dict[str, Any] = None,
        severity: str = "INFO"
    ):
        """Log a security event."""
        client_ip = self._get_client_ip(request)
        
        event = SecurityEvent(
            event_type=event_type,
            source_ip=client_ip,
            user_agent=request.headers.get("user-agent", ""),
            api_key_prefix=api_key_prefix,
            timestamp=datetime.utcnow(),
            details=details or {},
            severity=severity
        )
        
        self.security_events.append(event)
        
        # Log to structured logger
        logger.info(
            "Security event",
            event_type=event_type,
            source_ip=client_ip,
            api_key_prefix=api_key_prefix,
            severity=severity,
            details=details
        )
        
        # Handle failed authentication attempts
        if event_type == "authentication_failed":
            self._handle_failed_attempt(client_ip)
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded IP headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if hasattr(request.client, 'host'):
            return request.client.host
        
        return "unknown"
    
    def _handle_failed_attempt(self, ip: str):
        """Handle failed authentication attempt."""
        now = datetime.utcnow()
        
        # Initialize if not exists
        if ip not in self.failed_attempts:
            self.failed_attempts[ip] = []
        
        # Add current attempt
        self.failed_attempts[ip].append(now)
        
        # Clean old attempts outside window
        window_start = now - timedelta(minutes=self.attempt_window_minutes)
        self.failed_attempts[ip] = [
            attempt for attempt in self.failed_attempts[ip]
            if attempt > window_start
        ]
        
        # Check if should block
        if len(self.failed_attempts[ip]) >= self.max_failed_attempts:
            self.blocked_ips[ip] = now + timedelta(hours=self.block_duration_hours)
            logger.warning(
                "IP blocked due to failed attempts",
                ip=ip,
                attempts=len(self.failed_attempts[ip]),
                block_until=self.blocked_ips[ip].isoformat()
            )
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is currently blocked."""
        if ip not in self.blocked_ips:
            return False
        
        # Check if block has expired
        if datetime.utcnow() > self.blocked_ips[ip]:
            del self.blocked_ips[ip]
            return False
        
        return True
    
    def get_security_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get security events summary."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent_events = [e for e in self.security_events if e.timestamp > cutoff]
        
        # Group by event type
        event_counts = {}
        ip_counts = {}
        
        for event in recent_events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
            ip_counts[event.source_ip] = ip_counts.get(event.source_ip, 0) + 1
        
        return {
            "total_events": len(recent_events),
            "event_types": event_counts,
            "top_source_ips": sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "blocked_ips": len(self.blocked_ips),
            "failed_attempt_ips": len(self.failed_attempts)
        }


class ContentSecurityPolicy:
    """Content Security Policy headers and validation."""
    
    @staticmethod
    def get_csp_header() -> str:
        """Get CSP header value for API responses."""
        policies = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # Might be needed for docs
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-src 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        return "; ".join(policies)
    
    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get all security headers for responses."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY", 
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": ContentSecurityPolicy.get_csp_header(),
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "X-Permitted-Cross-Domain-Policies": "none"
        }


# Global security instances
input_sanitizer = InputSanitizer()
ip_whitelist = IPWhitelist()
security_auditor = SecurityAuditor()

# Optional request signer (requires secret key)
request_signer = None
settings = get_settings()
if settings.SECRET_KEY:
    request_signer = RequestSigner(settings.SECRET_KEY)


def validate_request_security(request: Request, api_key: str = "") -> bool:
    """Comprehensive request security validation."""
    try:
        client_ip = security_auditor._get_client_ip(request)
        
        # Check if IP is blocked
        if security_auditor.is_ip_blocked(client_ip):
            security_auditor.log_security_event(
                "blocked_ip_access_attempt",
                request,
                api_key[:8] if api_key else "",
                {"reason": "IP temporarily blocked"},
                "WARNING"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Access temporarily restricted"
            )
        
        # Check IP whitelist in production
        if settings.is_production() and not ip_whitelist.is_ip_allowed(client_ip):
            security_auditor.log_security_event(
                "unauthorized_ip_access",
                request,
                api_key[:8] if api_key else "",
                {"client_ip": client_ip},
                "WARNING"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied from this IP address"
            )
        
        # Validate User-Agent
        user_agent = request.headers.get("user-agent", "")
        if not user_agent or len(user_agent) > 500:
            security_auditor.log_security_event(
                "suspicious_user_agent",
                request,
                api_key[:8] if api_key else "",
                {"user_agent": user_agent[:100]},
                "WARNING"
            )
            # Don't block, just log
        
        # Check for suspicious headers
        suspicious_headers = ["X-Forwarded-Host", "X-Forwarded-Proto", "X-Original-URL"]
        for header in suspicious_headers:
            if header in request.headers:
                security_auditor.log_security_event(
                    "suspicious_header",
                    request,
                    api_key[:8] if api_key else "",
                    {"header": header, "value": request.headers[header][:100]},
                    "INFO"
                )
        
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Security validation error", error=str(e))
        return True  # Fail open for non-security errors


def sanitize_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize request data for security."""
    sanitized = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            # Apply appropriate sanitization based on field
            if key == "kvk_number":
                try:
                    sanitized[key] = input_sanitizer.sanitize_kvk_number(value)
                except ValueError as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid {key}: {str(e)}"
                    )
            elif key in ["search_query", "company_name"]:
                try:
                    sanitized[key] = input_sanitizer.sanitize_search_query(value)
                except ValueError as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid {key}: {str(e)}"
                    )
            else:
                # General string validation
                if not input_sanitizer.is_safe_string(value):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid content in field: {key}"
                    )
                sanitized[key] = value
        else:
            sanitized[key] = value
    
    return sanitized