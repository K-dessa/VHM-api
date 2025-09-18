import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, validator


class SearchDepth(str, Enum):
    """Enum for search depth options."""

    SIMPLE = "simple"
    STANDARD = "standard"
    DEEP = "deep"


class DateRange(str, Enum):
    """Enum for date range options."""

    LAST_YEAR = "last_year"
    LAST_3_YEARS = "last_3_years"
    LAST_5_YEARS = "last_5_years"
    ALL = "all"


class CompanyAnalysisRequest(BaseModel):
    """Request model for company analysis."""

    company_name: str = Field(
        ...,
        description="Juridische bedrijfsnaam van het bedrijf",
        example="ASML Holding N.V.",
        min_length=2,
        max_length=200
    )
    kvk_nummer: Optional[str] = Field(
        None,
        description="KVK nummer van het bedrijf (optioneel - nieuwe workflow gebruikt webcrawling)",
        example="12345678",
        min_length=8,
        max_length=8
    )
    contactpersoon: Optional[str] = Field(
        None,
        description="Naam van contactpersoon om ook in nieuws/rechtszaken te zoeken",
        example="John Doe",
        max_length=100
    )
    search_depth: SearchDepth = Field(
        default=SearchDepth.STANDARD,
        description="Depth of the analysis (simple < 15s, standard < 30s, deep < 40s)",
    )
    news_date_range: DateRange = Field(
        default=DateRange.LAST_YEAR, description="Date range for news analysis"
    )
    include_subsidiaries: bool = Field(
        default=False, description="Whether to include analysis of subsidiaries"
    )

    @validator("company_name")
    def validate_company_name(cls, v):
        """Validate company name format."""
        # Remove excessive whitespace
        clean_name = re.sub(r'\s+', ' ', v.strip())
        
        # Check minimum length
        if len(clean_name) < 2:
            raise ValueError("Company name must be at least 2 characters long")
        
        # Check for dangerous characters (basic security)
        dangerous_chars = ['<', '>', '"', "'", '\n', '\r', '\t']
        if any(char in clean_name for char in dangerous_chars):
            raise ValueError("Company name contains invalid characters")
        
        return clean_name

    @validator("kvk_nummer")
    def validate_kvk_nummer(cls, v):
        """Validate KVK number format."""
        if v is None:
            return v
        
        # Remove any whitespace or special characters
        clean_kvk = re.sub(r'\D', '', v)
        
        # Check if it's exactly 8 digits
        if len(clean_kvk) != 8:
            raise ValueError("KVK nummer must be exactly 8 digits")
        
        # Check if all characters are digits
        if not clean_kvk.isdigit():
            raise ValueError("KVK nummer must contain only digits")
        
        return clean_kvk

    @validator("contactpersoon")
    def validate_contactpersoon(cls, v):
        """Validate contact person name."""
        if v is None:
            return v
        
        # Remove excessive whitespace
        clean_name = re.sub(r'\s+', ' ', v.strip())
        
        # Check for dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '\n', '\r', '\t']
        if any(char in clean_name for char in dangerous_chars):
            raise ValueError("Contact person name contains invalid characters")
        
        return clean_name

    model_config = {
        "json_schema_extra": {
            "example": {
                "company_name": "ASML Holding N.V.",
                "kvk_nummer": "17014545",
                "contactpersoon": "Peter Wennink",
                "search_depth": "standard",
                "news_date_range": "last_year",
                "include_subsidiaries": False,
            }
        }
    }
