from typing import Any, Optional


class BusinessAnalysisError(Exception):
    """Base exception for business analysis API."""

    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ValidationError(BusinessAnalysisError):
    """Raised when input validation fails."""

    pass


class ExternalAPIError(BusinessAnalysisError):
    """Base class for external API errors."""

    def __init__(
        self,
        message: str,
        service: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        self.service = service
        self.status_code = status_code
        super().__init__(message, error_code)



class LegalAPIError(ExternalAPIError):
    """Raised when legal service (rechtspraak.nl) returns an error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        super().__init__(message, "Legal API", status_code, error_code)


class OpenAIAPIError(ExternalAPIError):
    """Raised when OpenAI API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        super().__init__(message, "OpenAI API", status_code, error_code)


class RateLimitError(BusinessAnalysisError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None
    ):
        self.retry_after = retry_after
        super().__init__(message)



class TimeoutError(BusinessAnalysisError):
    """Raised when an operation times out."""

    def __init__(self, message: str, service: Optional[str] = None):
        self.service = service
        super().__init__(message)
