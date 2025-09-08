from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class RiskLevel(str, Enum):
    """Risk level enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Address(BaseModel):
    """Company address information."""
    
    street: str = Field(..., description="Street name and number")
    house_number: Optional[str] = Field(None, description="House number")
    postal_code: str = Field(..., description="Postal code")
    city: str = Field(..., description="City name")
    country: str = Field(default="Nederland", description="Country name")


class SBICode(BaseModel):
    """Standard Business Industry (SBI) code."""
    
    code: str = Field(..., description="SBI code")
    description: str = Field(..., description="SBI code description")


class CompanyInfo(BaseModel):
    """Basic company information."""

    name: str = Field(..., description="Company name")
    trade_name: Optional[str] = Field(
        None, description="Trade name if different from official name"
    )
    legal_form: Optional[str] = Field(None, description="Legal form (BV, NV, etc.)")
    establishment_date: Optional[datetime] = Field(
        None, description="Date of establishment"
    )
    address: Optional[Address] = Field(None, description="Company address")
    sbi_codes: List[SBICode] = Field(
        default=[], description="Standard Business Industry codes"
    )
    business_activities: List[str] = Field(
        default=[], description="List of business activities (legacy field)"
    )
    employee_count: Optional[int] = Field(
        None, description="Number of employees", ge=0
    )
    employee_count_range: Optional[str] = Field(
        None, description="Employee count range"
    )
    annual_revenue_range: Optional[str] = Field(
        None, description="Annual revenue range"
    )
    website: Optional[str] = Field(
        None, description="Company website URL"
    )
    email: Optional[str] = Field(
        None, description="Company email address"
    )
    phone: Optional[str] = Field(
        None, description="Company phone number"
    )
    status: Optional[str] = Field(None, description="Company status (active, dissolved, etc.)")
    
    @validator('website')
    def validate_website(cls, v):
        """Validate website URL format."""
        if v and not v.startswith(('http://', 'https://')):
            return f"https://{v}"
        return v


class LegalCase(BaseModel):
    """Individual legal case information."""

    ecli: str = Field(..., description="European Case Law Identifier")
    case_number: str = Field(..., description="Court case number")
    date: datetime = Field(..., description="Date of the case/judgment")
    court: str = Field(..., description="Name of the court")
    type: str = Field(..., description="Type of legal case (civil, criminal, administrative)")
    parties: List[str] = Field(default=[], description="Parties involved in the case")
    summary: str = Field(..., description="Brief summary of the case")
    outcome: str = Field(default="unknown", description="Case outcome (won, lost, partial, unknown)")
    url: str = Field(..., description="URL to the full case details")
    relevance_score: float = Field(..., ge=0, le=1, description="Relevance score (0-1)")
    
    @validator('ecli')
    def validate_ecli(cls, v):
        """Validate ECLI format."""
        import re
        if not re.match(r'^ECLI:[A-Z]{2}:[A-Z0-9]+:\d{4}:[A-Z0-9.]+$', v):
            raise ValueError("Invalid ECLI format")
        return v


class LegalFindings(BaseModel):
    """Legal analysis results."""

    total_cases: int = Field(..., description="Total number of cases found")
    risk_level: str = Field(..., description="Legal risk level (low, medium, high)")
    cases: List[LegalCase] = Field(
        default=[], description="List of relevant legal cases"
    )
    search_window: Optional[str] = Field(
        None, description="Date range used for the search (YYYY-MM-DD to YYYY-MM-DD)"
    )
    results_count: Optional[int] = Field(
        None, description="Number of ECLI entries retrieved before filtering"
    )


class NewsArticle(BaseModel):
    """Individual news article with enhanced analysis."""

    title: str = Field(..., description="News article title")
    source: str = Field(..., description="News source")
    date: datetime = Field(..., description="Publication date")
    url: Optional[str] = Field(None, description="Link to original article")
    summary: str = Field(..., description="AI-generated article summary", max_length=500)
    sentiment_score: float = Field(
        ..., ge=-1, le=1, description="Sentiment score (-1.0 to 1.0)"
    )
    relevance_score: float = Field(
        ..., ge=0, le=1, description="Relevance score (0.0 to 1.0)"
    )
    categories: List[str] = Field(
        default=[], description="Article categories (financial, legal, operational, etc.)"
    )
    key_phrases: List[str] = Field(
        default=[], description="Key phrases extracted from the article"
    )
    trust_score: Optional[float] = Field(
        None, ge=0, le=1, description="Source trust score"
    )
    
    @validator('url')
    def validate_url(cls, v):
        """Validate URL format."""
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v


class NewsItem(NewsArticle):
    """Backward compatibility alias for NewsArticle."""
    pass


class PositiveNews(BaseModel):
    """Positive news analysis summary."""
    
    count: int = Field(..., description="Number of positive articles", ge=0)
    average_sentiment: float = Field(
        ..., ge=0, le=1, description="Average positive sentiment score"
    )
    articles: List[NewsArticle] = Field(
        default=[], description="List of positive news articles"
    )


class NegativeNews(BaseModel):
    """Negative news analysis summary."""
    
    count: int = Field(..., description="Number of negative articles", ge=0)
    average_sentiment: float = Field(
        ..., ge=-1, le=0, description="Average negative sentiment score"
    )
    articles: List[NewsArticle] = Field(
        default=[], description="List of negative news articles"
    )


class NewsAnalysis(BaseModel):
    """Enhanced news analysis results with positive/negative breakdown."""

    positive_news: PositiveNews = Field(..., description="Positive news analysis")
    negative_news: NegativeNews = Field(..., description="Negative news analysis")
    overall_sentiment: float = Field(
        ..., ge=-1, le=1, description="Overall sentiment score"
    )
    sentiment_summary: Optional[Dict[str, float]] = Field(
        None, description="Sentiment breakdown (positive, neutral, negative percentages)"
    )
    total_relevance: float = Field(
        ..., ge=0, le=1, description="Overall relevance score"
    )
    total_articles_found: int = Field(..., description="Total number of articles found")
    articles: List[NewsArticle] = Field(
        default=[], description="All relevant news articles (for backward compatibility)"
    )
    key_topics: List[str] = Field(
        default=[], description="Key topics identified in news"
    )
    risk_indicators: List[str] = Field(
        default=[], description="Risk indicators from news"
    )
    summary: str = Field(..., description="Overall news analysis summary")
    
    @validator('articles', pre=True, always=True)
    def combine_articles(cls, v, values):
        """Combine positive and negative articles for backward compatibility."""
        if v:
            return v
        
        all_articles = []
        if 'positive_news' in values and values['positive_news']:
            all_articles.extend(values['positive_news'].articles)
        if 'negative_news' in values and values['negative_news']:
            all_articles.extend(values['negative_news'].articles)
        
        # Sort by relevance and sentiment
        all_articles.sort(
            key=lambda x: (x.relevance_score, abs(x.sentiment_score)),
            reverse=True
        )
        
        return all_articles


class RiskAssessment(BaseModel):
    """Overall risk assessment."""

    overall_risk_level: RiskLevel = Field(..., description="Overall risk level")
    risk_score: float = Field(..., ge=0, le=100, description="Risk score (0-100)")
    risk_factors: List[str] = Field(default=[], description="Identified risk factors")
    positive_factors: List[str] = Field(default=[], description="Positive factors")
    recommendations: List[str] = Field(default=[], description="Recommendations")
    confidence_level: float = Field(
        ..., ge=0, le=1, description="Confidence in assessment"
    )


class CrawledContent(BaseModel):
    """Individual crawled page content."""
    
    url: str = Field(..., description="URL of the crawled page")
    title: str = Field(..., description="Page title")
    content: str = Field(..., description="Extracted markdown content")
    links: List[str] = Field(default=[], description="Internal links found on page")
    crawl_timestamp: float = Field(..., description="Timestamp when page was crawled")
    content_length: int = Field(..., description="Length of extracted content")
    language: str = Field(default="en", description="Detected language (nl/en)")


class WebContent(BaseModel):
    """Aggregated web content from Crawl4AI."""
    
    company_name: str = Field(..., description="Company name that was searched")
    website_url: str = Field(..., description="Main website URL found")
    pages_crawled: int = Field(..., description="Number of pages successfully crawled")
    content_summary: str = Field(..., description="Brief summary of crawled content")
    
    main_sections: List[str] = Field(
        default=[], 
        description="Key content sections extracted from website"
    )
    business_activities: List[str] = Field(
        default=[], 
        description="Business activities identified from content"
    )
    contact_info: Dict[str, str] = Field(
        default={}, 
        description="Contact information extracted (email, phone, etc.)"
    )
    
    crawled_pages: List[CrawledContent] = Field(
        default=[], 
        description="Individual page data (limited for response size)"
    )


class CompanyAnalysisResponse(BaseModel):
    """Complete company analysis response."""

    request_id: str = Field(..., description="Unique request identifier")
    analysis_timestamp: datetime = Field(
        ..., description="When the analysis was performed"
    )
    processing_time_seconds: float = Field(..., description="Total processing time")

    company_info: CompanyInfo = Field(..., description="Basic company information")
    legal_findings: Optional[LegalFindings] = Field(
        None, description="Legal analysis results"
    )
    news_analysis: Optional[NewsAnalysis] = Field(
        None, description="News analysis results"
    )
    web_content: Optional[WebContent] = Field(
        None, description="Crawled website content from Crawl4AI"
    )
    risk_assessment: RiskAssessment = Field(..., description="Overall risk assessment")

    warnings: List[str] = Field(
        default=[], description="Any warnings about the analysis"
    )
    data_sources: List[str] = Field(default=[], description="Data sources used")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    request_id: Optional[str] = Field(None, description="Request ID if available")
    timestamp: datetime = Field(..., description="Error timestamp")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )


class NewsItem(BaseModel):
    """Individual news item for simplified response."""
    
    titel: str = Field(..., description="News article title")
    link: str = Field(..., description="Link to the article")
    bron: Optional[str] = Field(None, description="Source: 'rechtspraak.nl' or news source")


class CompanyAnalysisSimpleResponse(BaseModel):
    """Simplified company analysis response matching the new workflow."""
    
    bedrijf: str = Field(..., description="Company name")
    samenvatting: str = Field(..., description="Brief summary of the analysis")
    goed_nieuws: List[NewsItem] = Field(default=[], description="List of positive news")
    slecht_nieuws: List[NewsItem] = Field(default=[], description="List of negative news including ECLI cases")


class NieuwsItem(BaseModel):
    """Nederlandse nieuwsitem met bron en link."""
    
    titel: str = Field(..., description="Titel van het nieuwsartikel", max_length=200)
    link: str = Field(..., description="Link naar het artikel")
    bron: str = Field(..., description="Bron van het artikel (bijv. 'fd.nl', 'rechtspraak.nl')")
    
    @validator('link')
    def validate_link(cls, v):
        """Validate link format."""
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError("Link moet beginnen met http:// of https://")
        return v


class NederlandseAnalyseResponse(BaseModel):
    """Nederlandse bedrijfsanalyse response volgens jouw specificatie."""
    
    bedrijfsnaam: str = Field(..., description="Naam van het bedrijf")
    kvk_nummer: Optional[str] = Field(None, description="KVK nummer indien opgegeven")
    contactpersoon: str = Field(..., description="Contactpersoon indien opgegeven, anders '-'")
    
    goed_nieuws: List[NieuwsItem] = Field(
        default=[], 
        description="Lijst van positieve nieuwsberichten met titel, bron en link"
    )
    slecht_nieuws: List[NieuwsItem] = Field(
        default=[], 
        description="Lijst van negatieve nieuwsberichten inclusief rechtszaken"
    )
    samenvatting: str = Field(
        ..., 
        description="Neutrale samenvatting van de analyse in 2-3 zinnen",
        max_length=500
    )
    
    # Metadata (optional)
    analysis_timestamp: Optional[datetime] = Field(None, description="Tijdstip van analyse")
    bronnen_gecontroleerd: List[str] = Field(
        default=[], 
        description="Lijst van gecontroleerde bronnen"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "bedrijfsnaam": "ASML Holding N.V.",
                "kvk_nummer": "17014545", 
                "contactpersoon": "Peter Wennink",
                "goed_nieuws": [
                    {
                        "titel": "ASML boekt sterke kwartaalcijfers met recordomzet",
                        "link": "https://fd.nl/ondernemen/asml-kwartaal-resultaten",
                        "bron": "fd.nl"
                    }
                ],
                "slecht_nieuws": [
                    {
                        "titel": "ASML geconfronteerd met export restricties naar China", 
                        "link": "https://nos.nl/nieuws/asml-china-restricties",
                        "bron": "nos.nl"
                    },
                    {
                        "titel": "Rechtszaak aangespannen tegen ASML betreffende patentschending",
                        "link": "https://rechtspraak.nl/uitspraken/ECLI:NL:RBOBR:2024:1234",
                        "bron": "rechtspraak.nl"
                    }
                ],
                "samenvatting": "Analyse van 3 artikelen voor ASML Holding N.V. 1 positief artikel gevonden, 2 negatieve items gevonden inclusief 1 rechtszaak. Overall sentiment is neutraal.",
                "bronnen_gecontroleerd": ["rechtspraak.nl", "fd.nl", "nos.nl", "nrc.nl"]
            }
        }
    }


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    version: str = Field(..., description="API version")
    dependencies: Dict[str, str] = Field(
        ..., description="Status of external dependencies"
    )
    uptime_seconds: float = Field(..., description="Service uptime in seconds")


class AnalysisResponse(BaseModel):
    """Generic analysis response model."""
    
    request_id: str = Field(..., description="Unique request identifier")
    timestamp: float = Field(..., description="Analysis timestamp")
    company_name: str = Field(..., description="Company name analyzed")
    analysis_type: str = Field(..., description="Type of analysis performed")
    status: str = Field(..., description="Analysis status")
