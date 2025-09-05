"""
Rate limiting utilities for API endpoints.
"""

import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from threading import Lock

from app.core.config import settings
from app.core.exceptions import RateLimitError


@dataclass
class RateLimitInfo:
    """Information about current rate limit status."""
    
    requests_made: int
    window_start: float
    window_size: int
    limit: int
    
    @property
    def remaining(self) -> int:
        """Number of requests remaining in current window."""
        return max(0, self.limit - self.requests_made)
    
    @property
    def reset_time(self) -> float:
        """When the current window resets (Unix timestamp)."""
        return self.window_start + self.window_size
    
    @property
    def is_exceeded(self) -> bool:
        """Whether the rate limit has been exceeded."""
        return self.requests_made >= self.limit


class InMemoryRateLimiter:
    """
    In-memory rate limiter implementation.
    
    This is a simple sliding window rate limiter that tracks requests per API key.
    For production use, consider implementing a Redis-based rate limiter for
    better performance and persistence across instances.
    """
    
    def __init__(
        self,
        requests_per_window: int = None,
        window_size: int = None
    ):
        self.requests_per_window = requests_per_window or settings.RATE_LIMIT_REQUESTS
        self.window_size = window_size or settings.RATE_LIMIT_WINDOW
        
        # Storage: {api_key: RateLimitInfo}
        self._storage: Dict[str, RateLimitInfo] = {}
        self._lock = Lock()
    
    def check_rate_limit(self, api_key: str) -> RateLimitInfo:
        """
        Check if API key has exceeded rate limit.
        
        Args:
            api_key: The API key to check
            
        Returns:
            RateLimitInfo with current status
            
        Raises:
            RateLimitError: If rate limit is exceeded
        """
        with self._lock:
            now = time.time()
            
            # Get or create rate limit info for this API key
            if api_key not in self._storage:
                self._storage[api_key] = RateLimitInfo(
                    requests_made=0,
                    window_start=now,
                    window_size=self.window_size,
                    limit=self.requests_per_window
                )
            
            rate_info = self._storage[api_key]
            
            # Check if we need to reset the window
            if now >= rate_info.window_start + rate_info.window_size:
                rate_info.requests_made = 0
                rate_info.window_start = now
            
            # Check if limit is exceeded
            if rate_info.is_exceeded:
                retry_after = int(rate_info.reset_time - now) + 1
                raise RateLimitError(
                    f"Rate limit exceeded for API key. Limit: {rate_info.limit} "
                    f"requests per {rate_info.window_size} seconds",
                    retry_after=retry_after
                )
            
            # Increment request count
            rate_info.requests_made += 1
            
            return rate_info
    
    def get_rate_limit_info(self, api_key: str) -> Optional[RateLimitInfo]:
        """
        Get current rate limit info without incrementing counter.
        
        Args:
            api_key: The API key to check
            
        Returns:
            RateLimitInfo if exists, None otherwise
        """
        with self._lock:
            if api_key not in self._storage:
                return None
            
            now = time.time()
            rate_info = self._storage[api_key]
            
            # Check if we need to reset the window
            if now >= rate_info.window_start + rate_info.window_size:
                rate_info.requests_made = 0
                rate_info.window_start = now
            
            return rate_info
    
    def reset_rate_limit(self, api_key: str) -> None:
        """
        Reset rate limit for a specific API key.
        
        Args:
            api_key: The API key to reset
        """
        with self._lock:
            if api_key in self._storage:
                del self._storage[api_key]
    
    def get_rate_limit_headers(self, api_key: str) -> Dict[str, str]:
        """
        Get rate limit headers for HTTP response.
        
        Args:
            api_key: The API key to get headers for
            
        Returns:
            Dictionary of rate limit headers
        """
        rate_info = self.get_rate_limit_info(api_key)
        
        if not rate_info:
            # Return default headers if no rate info exists yet
            return {
                "X-RateLimit-Limit": str(self.requests_per_window),
                "X-RateLimit-Remaining": str(self.requests_per_window),
                "X-RateLimit-Reset": str(int(time.time() + self.window_size)),
                "X-RateLimit-Window": str(self.window_size)
            }
        
        return {
            "X-RateLimit-Limit": str(rate_info.limit),
            "X-RateLimit-Remaining": str(rate_info.remaining),
            "X-RateLimit-Reset": str(int(rate_info.reset_time)),
            "X-RateLimit-Window": str(rate_info.window_size)
        }
    
    def cleanup_expired(self) -> None:
        """Remove expired rate limit entries to prevent memory leaks."""
        with self._lock:
            now = time.time()
            expired_keys = []
            
            for api_key, rate_info in self._storage.items():
                # Consider entries expired if they haven't been used in 2x window size
                if now > rate_info.window_start + (rate_info.window_size * 2):
                    expired_keys.append(api_key)
            
            for key in expired_keys:
                del self._storage[key]
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about current rate limiter state.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            total_keys = len(self._storage)
            active_keys = 0
            total_requests = 0
            
            now = time.time()
            for rate_info in self._storage.values():
                if now < rate_info.window_start + rate_info.window_size:
                    active_keys += 1
                    total_requests += rate_info.requests_made
            
            return {
                "total_api_keys": total_keys,
                "active_api_keys": active_keys,
                "total_requests": total_requests,
                "requests_per_window": self.requests_per_window,
                "window_size": self.window_size
            }


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get the global rate limiter instance."""
    return rate_limiter