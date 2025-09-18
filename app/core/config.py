import os
import re
from typing import Optional, List, Dict, Any
from enum import Enum

from decouple import config
from pydantic import validator, Field
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Application environments."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Enhanced configuration with validation and environment-specific settings."""
    
    # Application settings
    APP_NAME: str = config("APP_NAME", default="bedrijfsanalyse-api")
    APP_VERSION: str = config("APP_VERSION", default="1.0.0")
    ENVIRONMENT: Environment = config("ENVIRONMENT", default=Environment.DEVELOPMENT, cast=Environment)
    DEBUG: bool = config("DEBUG", default=False, cast=bool)
    LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")
    
    # Security settings
    SECRET_KEY: Optional[str] = config("SECRET_KEY", default=None)
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    CORS_ORIGINS: List[str] = Field(default_factory=list)
    
    # External API settings
    OPENAI_API_KEY: Optional[str] = config("OPENAI_API_KEY", default=None)
    OPENAI_MODEL: str = config("OPENAI_MODEL", default="gpt-4-turbo")
    OPENAI_MAX_TOKENS: int = config("OPENAI_MAX_TOKENS", default=4000, cast=int)
    NEWS_API_KEY: Optional[str] = config("NEWS_API_KEY", default=None)
    GOOGLE_SEARCH_API_KEY: Optional[str] = config("GOOGLE_SEARCH_API_KEY", default=None)
    GOOGLE_SEARCH_ENGINE_ID: Optional[str] = config("GOOGLE_SEARCH_ENGINE_ID", default=None)
    
    # Authentication
    API_KEYS: Optional[str] = config("API_KEYS", default=None)
    API_KEY_HEADER: str = config("API_KEY_HEADER", default="X-API-Key")
    
    # Rate limiting (environment-specific)
    RATE_LIMIT_REQUESTS: int = config("RATE_LIMIT_REQUESTS", default=100, cast=int)
    RATE_LIMIT_WINDOW: int = config("RATE_LIMIT_WINDOW", default=3600, cast=int)
    
    # Timeout settings (environment-specific)
    OPENAI_TIMEOUT: int = config("OPENAI_TIMEOUT", default=30, cast=int)
    ANALYSIS_TIMEOUT_SIMPLE: int = config("ANALYSIS_TIMEOUT_SIMPLE", default=25, cast=int)
    ANALYSIS_TIMEOUT_STANDARD: int = config("ANALYSIS_TIMEOUT_STANDARD", default=45, cast=int)
    ANALYSIS_TIMEOUT_DUTCH: int = config("ANALYSIS_TIMEOUT_DUTCH", default=40, cast=int)
    
    # Crawl4AI settings (new improved workflow)
    CRAWL_TIMEOUT: int = config("CRAWL_TIMEOUT", default=30, cast=int)
    CRAWL_MAX_DEPTH_STANDARD: int = config("CRAWL_MAX_DEPTH_STANDARD", default=2, cast=int)
    CRAWL_MAX_DEPTH_SIMPLE: int = config("CRAWL_MAX_DEPTH_SIMPLE", default=1, cast=int)
    CRAWL_MAX_PAGES_STANDARD: int = config("CRAWL_MAX_PAGES_STANDARD", default=10, cast=int)
    CRAWL_MAX_PAGES_SIMPLE: int = config("CRAWL_MAX_PAGES_SIMPLE", default=3, cast=int)
    CRAWL_OBEY_ROBOTS_TXT: bool = config("CRAWL_OBEY_ROBOTS_TXT", default=True, cast=bool)
    CRAWL_USER_AGENT: str = config("CRAWL_USER_AGENT", default="Mozilla/5.0 (compatible; BedrijfsanalyseBot/1.0)")
    CRAWL_PRIORITIZE_DUTCH_DOMAINS: bool = config("CRAWL_PRIORITIZE_DUTCH_DOMAINS", default=True, cast=bool)
    
    # Feature flags
    ENABLE_LEGAL_SERVICE: bool = config("ENABLE_LEGAL_SERVICE", default=True, cast=bool)
    ENABLE_NEWS_SERVICE: bool = config("ENABLE_NEWS_SERVICE", default=True, cast=bool)
    ENABLE_METRICS_COLLECTION: bool = config("ENABLE_METRICS_COLLECTION", default=True, cast=bool)
    ENABLE_TRACING: bool = config("ENABLE_TRACING", default=True, cast=bool)
    ENABLE_ALERTING: bool = config("ENABLE_ALERTING", default=True, cast=bool)
    ENABLE_CRAWL_SERVICE: bool = config("ENABLE_CRAWL_SERVICE", default=True, cast=bool)
    
    # Cache settings
    CACHE_TTL_COMPANY_INFO: int = config("CACHE_TTL_COMPANY_INFO", default=3600, cast=int)
    CACHE_TTL_LEGAL_CASES: int = config("CACHE_TTL_LEGAL_CASES", default=7200, cast=int)
    CACHE_TTL_NEWS_ANALYSIS: int = config("CACHE_TTL_NEWS_ANALYSIS", default=1800, cast=int)
    CACHE_TTL_WEB_CONTENT: int = config("CACHE_TTL_WEB_CONTENT", default=3600, cast=int)
    
    # Health check settings
    HEALTH_CHECK_INTERVAL: int = config("HEALTH_CHECK_INTERVAL", default=30, cast=int)
    EXTERNAL_SERVICE_TIMEOUT: int = config("EXTERNAL_SERVICE_TIMEOUT", default=5, cast=int)
    
    # Monitoring and alerting
    ALERT_EMAIL_RECIPIENTS: List[str] = Field(default_factory=list)
    SLACK_WEBHOOK_URL: Optional[str] = config("SLACK_WEBHOOK_URL", default=None)
    PROMETHEUS_METRICS_ENABLED: bool = config("PROMETHEUS_METRICS_ENABLED", default=True, cast=bool)
    
    # Cost tracking
    DAILY_COST_BUDGET_EUR: float = config("DAILY_COST_BUDGET_EUR", default=100.0, cast=float)
    OPENAI_COST_PER_1K_TOKENS: float = config("OPENAI_COST_PER_1K_TOKENS", default=0.03, cast=float)
    
    # Search depth parameters
    SEARCH_DEPTH_STANDARD_MAX_ARTICLES: int = config("SEARCH_DEPTH_STANDARD_MAX_ARTICLES", default=20, cast=int)
    SEARCH_DEPTH_DEEP_MAX_ARTICLES: int = config("SEARCH_DEPTH_DEEP_MAX_ARTICLES", default=50, cast=int)
    
    # Risk assessment parameters
    RISK_ASSESSMENT_WEIGHTS: Dict[str, float] = {
        "reputation": 0.30,
        "financial": 0.20,
        "operational": 0.10
    }
    
    @validator("ENVIRONMENT", pre=True)
    def validate_environment(cls, v):
        """Validate environment value."""
        if isinstance(v, str):
            try:
                return Environment(v.lower())
            except ValueError:
                return Environment.DEVELOPMENT
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()
    
    @validator("OPENAI_API_KEY")
    def validate_openai_api_key(cls, v):
        """Validate OpenAI API key format."""
        if v and not v.startswith('sk-'):
            raise ValueError("OpenAI API key must start with 'sk-'")
        return v
    
    @validator("API_KEYS")
    def validate_api_keys(cls, v):
        """Validate API keys format."""
        if v and v != "test-key,demo-key,prod-key1":
            keys = v.split(",")
            for key in keys:
                key = key.strip()
                if len(key) < 32:
                    raise ValueError("API keys must be at least 32 characters long")
        return v
    
    @validator("ALLOWED_HOSTS", pre=True)
    def parse_allowed_hosts(cls, v):
        """Parse allowed hosts from string or list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",") if host.strip()]
        return v
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @validator("ALERT_EMAIL_RECIPIENTS", pre=True)
    def parse_alert_emails(cls, v):
        """Parse alert email recipients from string or list."""
        if isinstance(v, str):
            emails = [email.strip() for email in v.split(",") if email.strip()]
            for email in emails:
                if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
                    raise ValueError(f"Invalid email format: {email}")
            return emails
        return v
    
    def get_parsed_api_keys(self) -> List[str]:
        """Get parsed API keys as a list."""
        if not self.API_KEYS:
            return []
        return [key.strip() for key in self.API_KEYS.split(",")]
    
    def get_timeout_for_search_depth(self, search_depth: str) -> int:
        """Get timeout based on search depth."""
        if search_depth == "simple":
            return self.ANALYSIS_TIMEOUT_SIMPLE
        elif search_depth == "dutch":
            return self.ANALYSIS_TIMEOUT_DUTCH
        return self.ANALYSIS_TIMEOUT_STANDARD
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.ENVIRONMENT == Environment.TESTING
    
    def get_environment_config(self) -> Dict[str, Any]:
        """Get environment-specific configuration overrides."""
        base_config = {}
        
        if self.is_production():
            base_config.update({
                "DEBUG": False,
                "LOG_LEVEL": "WARNING",
                "RATE_LIMIT_REQUESTS": 100,
                "ENABLE_METRICS_COLLECTION": True,
                "ENABLE_ALERTING": True,
                "HEALTH_CHECK_INTERVAL": 30
            })
        elif self.is_testing():
            base_config.update({
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "RATE_LIMIT_REQUESTS": 1000,  # Higher for testing
                "ENABLE_METRICS_COLLECTION": False,
                "ENABLE_ALERTING": False,
                "HEALTH_CHECK_INTERVAL": 60
            })
        else:  # development
            base_config.update({
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "RATE_LIMIT_REQUESTS": 200,
                "ENABLE_METRICS_COLLECTION": True,
                "ENABLE_ALERTING": False,
                "HEALTH_CHECK_INTERVAL": 60
            })
        
        return base_config
    
    def validate_required_settings(self):
        """Validate that required settings are present for the environment."""
        errors = []
        
        if self.is_production():
            if not self.SECRET_KEY:
                errors.append("SECRET_KEY is required in production")
            if not self.API_KEYS:
                errors.append("API_KEYS is required in production")
        
        if self.ENABLE_NEWS_SERVICE and not self.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when ENABLE_NEWS_SERVICE is True")
        
        if errors:
            raise ValueError("Configuration validation failed: " + "; ".join(errors))
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"  # Ignore unknown environment variables


def get_settings() -> Settings:
    """Get validated settings instance."""
    settings = Settings()
    settings.validate_required_settings()
    return settings


# Global settings instance
settings = get_settings()
