"""
API dependencies for authentication, authorization, and rate limiting.
"""

from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings
from app.utils.rate_limiter import get_rate_limiter, RateLimitInfo
import structlog

logger = structlog.get_logger(__name__)

# Security scheme for API key authentication
security = HTTPBearer(auto_error=False)

# Valid API keys (in production, these would come from a database)
VALID_API_KEYS = {
    "test-key": {"name": "Test Client", "permissions": ["read", "analyze"]},
    "demo-key": {"name": "Demo Client", "permissions": ["read"]},
    "test-api-key-12345678901234567890": {"name": "Production Test Client", "permissions": ["read", "analyze"]},
}


def load_api_keys_from_config():
    """Load API keys from configuration."""
    global VALID_API_KEYS
    
    # Check if API keys are configured via environment
    if hasattr(settings, 'API_KEYS') and settings.API_KEYS:
        api_keys = settings.API_KEYS.split(',')
        for key in api_keys:
            key = key.strip()
            if key and key not in VALID_API_KEYS:
                VALID_API_KEYS[key] = {
                    "name": f"Client {key[:8]}...",
                    "permissions": ["read", "analyze"]
                }


# Load API keys on import
load_api_keys_from_config()


async def get_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Extract and validate API key from request headers.
    
    Supports two authentication methods:
    1. X-API-Key header
    2. Bearer token in Authorization header
    
    Args:
        x_api_key: API key from X-API-Key header
        authorization: Bearer token from Authorization header
        
    Returns:
        Valid API key string
        
    Raises:
        HTTPException: If API key is missing, invalid, or unauthorized
    """
    api_key = None
    
    # Try X-API-Key header first
    if x_api_key:
        api_key = x_api_key.strip()
    
    # Fall back to Bearer token
    elif authorization and authorization.credentials:
        api_key = authorization.credentials.strip()
    
    # No API key provided
    if not api_key:
        logger.warning("API request without authentication")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Validate API key
    if api_key not in VALID_API_KEYS:
        logger.warning("Invalid API key used", api_key_prefix=api_key[:8])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    logger.info("Authenticated request", 
                client_name=VALID_API_KEYS[api_key]["name"],
                api_key_prefix=api_key[:8])
    
    return api_key


async def check_permissions(
    api_key: str = Depends(get_api_key),
    required_permission: str = "read"
) -> str:
    """
    Check if API key has required permissions.
    
    Args:
        api_key: Validated API key
        required_permission: Required permission level
        
    Returns:
        API key if authorized
        
    Raises:
        HTTPException: If API key lacks required permissions
    """
    client_info = VALID_API_KEYS[api_key]
    permissions = client_info.get("permissions", [])
    
    if required_permission not in permissions:
        logger.warning(
            "Insufficient permissions",
            client_name=client_info["name"],
            required=required_permission,
            available=permissions
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {required_permission}"
        )
    
    return api_key


async def rate_limit_dependency(
    api_key: str = Depends(get_api_key)
) -> RateLimitInfo:
    """
    Apply rate limiting to API requests.
    
    Args:
        api_key: Validated API key
        
    Returns:
        RateLimitInfo with current status
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    try:
        limiter = get_rate_limiter()
        rate_info = limiter.check_rate_limit(api_key)
        
        logger.info(
            "Rate limit check passed",
            api_key_prefix=api_key[:8],
            requests_made=rate_info.requests_made,
            remaining=rate_info.remaining
        )
        
        return rate_info
        
    except Exception as e:
        from app.core.exceptions import RateLimitError
        
        if isinstance(e, RateLimitError):
            logger.warning(
                "Rate limit exceeded",
                api_key_prefix=api_key[:8],
                retry_after=e.retry_after
            )
            
            headers = {"Retry-After": str(e.retry_after)} if e.retry_after else {}
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=e.message,
                headers=headers
            )
        
        # Re-raise unexpected errors
        raise


async def analyze_permission_dependency(
    api_key: str = Depends(get_api_key)
) -> str:
    """
    Dependency that requires 'analyze' permission.
    
    Args:
        api_key: API key from authentication
        
    Returns:
        API key if authorized for analysis
    """
    return await check_permissions(api_key, "analyze")


async def authenticated_with_rate_limit(
    api_key: str = Depends(analyze_permission_dependency),
    rate_info: RateLimitInfo = Depends(rate_limit_dependency)
) -> tuple[str, RateLimitInfo]:
    """
    Combined dependency for authentication, authorization, and rate limiting.
    
    Args:
        api_key: Validated API key with analyze permissions
        rate_info: Rate limit information
        
    Returns:
        Tuple of (api_key, rate_info)
    """
    return api_key, rate_info


def get_client_info(api_key: str) -> dict:
    """
    Get client information for an API key.
    
    Args:
        api_key: The API key to look up
        
    Returns:
        Client information dictionary
    """
    return VALID_API_KEYS.get(api_key, {"name": "Unknown", "permissions": []})