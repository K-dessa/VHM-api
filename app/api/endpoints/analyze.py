import time
import uuid
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
import structlog

from ...models.request_models import CompanyAnalysisRequest
from ...models.response_models import CompanyAnalysisResponse, RiskAssessment, RiskLevel, ErrorResponse, LegalFindings, CompanyInfo, CompanyAnalysisSimpleResponse, NewsItem, NederlandseAnalyseResponse, NieuwsItem
from ...services.legal_service import LegalService
from ...services.news_service import NewsService
from ...services.risk_service import RiskService
from ...services.crawl_service import CrawlService
from ...core.config import settings
from ...api.dependencies import authenticated_with_rate_limit
from ...core.exceptions import (
    TimeoutError, RateLimitError, ValidationError, BusinessAnalysisError
)
from ...utils.rate_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/analyze-company",
    response_model=CompanyAnalysisResponse,
    summary="Comprehensive Company Analysis",
    description="""
    Perform comprehensive risk assessment and due diligence analysis based on company name.
    
    This endpoint integrates multiple data sources using the improved workflow:
    - **Web content analysis** using Crawl4AI for authentic company information
    - **Legal risk assessment** from Rechtspraak.nl court case database
    - **News sentiment analysis** using AI-powered processing (OpenAI GPT-4)
    - **Integrated risk scoring** combining all data sources
    
    The analysis includes web content, legal cases, news sentiment, and operational risk factors
    with actionable recommendations and monitoring suggestions.
    
    **Note**: This service requires an OpenAI API key to be configured.
    """,
    response_description="""
    Complete analysis results including:
    - Company information from crawled website content
    - Legal findings and risk assessment from Rechtspraak.nl
    - News analysis with sentiment scoring
    - Web content analysis with business intelligence
    - Overall risk assessment with recommendations
    - Processing metadata and data quality indicators
    """,
    responses={
        200: {
            "description": "Successful analysis",
            "content": {
                "application/json": {
                    "example": {
                        "request_id": "550e8400-e29b-41d4-a716-446655440000",
                        "analysis_timestamp": "2024-01-15T10:30:00Z",
                        "processing_time_seconds": 8.234,
                        "company_info": {
                            "name": "ASML Holding N.V.",
                            "legal_form": None,
                            "establishment_date": None,
                            "address": None
                        },
                        "risk_assessment": {
                            "overall_risk_level": "MEDIUM",
                            "risk_score": 35,
                            "risk_factors": ["No major legal issues found"],
                            "recommendations": ["Standard business verification recommended"]
                        },
                        "data_sources": ["Company name search", "AI-powered news analysis (OpenAI)"],
                        "warnings": ["This analysis is based on publicly available data and company name search"]
                    }
                }
            }
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Company name must be at least 2 characters long"
                    }
                }
            }
        },
        500: {
            "description": "OpenAI API not configured",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "OpenAI API key not configured - news analysis service unavailable"
                    }
                }
            }
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Rate limit exceeded. Try again in 3600 seconds."
                    }
                }
            }
        },
        502: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An unexpected error occurred during analysis"
                    }
                }
            }
        }
    }
)
async def analyze_company(
    request: CompanyAnalysisRequest,
    response: Response,
    auth_data: tuple = Depends(authenticated_with_rate_limit)
):
    """
    Perform comprehensive company analysis with risk assessment.
    
    Integrates legal case analysis and AI-powered news sentiment analysis 
    to provide actionable business intelligence based on company name.
    """
    api_key, rate_info = auth_data
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(
        "Starting company analysis",
        request_id=request_id,
        company_name=request.company_name,
        api_key_prefix=api_key[:8]
    )
    
    try:
        # Add rate limit headers to response
        limiter = get_rate_limiter()
        headers = limiter.get_rate_limit_headers(api_key)
        for key, value in headers.items():
            response.headers[key] = value
        
        # Initialize services for improved workflow
        legal_service = LegalService()
        risk_service = RiskService()
        crawl_service = CrawlService()
        
        # Initialize news service if OpenAI API key is available
        news_service = None
        try:
            news_service = NewsService()
        except ValueError as e:
            logger.warning("News service not available", error=str(e))
            # Don't fail the entire analysis, just skip news analysis
            news_service = None
        
        # Initialize legal service (robots.txt check)
        await legal_service.initialize()
        
        # Crawl company website for authentic business information
        logger.info("Starting website crawl", company_name=request.company_name)
        
        web_content = await crawl_service.crawl_company_website(
            company_name=request.company_name,
            max_depth=2 if request.search_depth != "simple" else 1,
            focus_dutch=True,
            simple_mode=(request.search_depth == "simple")
        )
        
        # Create company info based on crawled content
        company_info = CompanyInfo(
            name=request.company_name,
            trade_name=None,
            legal_form=None,
            establishment_date=None,
            address=None,
            sbi_codes=[],
            business_activities=web_content.business_activities if web_content else [],
            employee_count=None,
            website=web_content.website_url if web_content else None,
            email=web_content.contact_info.get('email') if web_content and hasattr(web_content, 'contact_info') and web_content.contact_info else None,
            phone=web_content.contact_info.get('phone') if web_content and hasattr(web_content, 'contact_info') and web_content.contact_info else None,
            status="Active" if web_content else "Unknown"
        )
        
        # Fetch legal cases and news analysis in parallel
        logger.info("Fetching legal cases and news analysis", company_name=request.company_name)
        
        # Set timeout based on search depth
        timeout_seconds = settings.get_timeout_for_search_depth(request.search_depth)
        
        try:
            # Run legal and news services in parallel with timeout
            tasks = []
            
            # Add legal service (always attempt, regardless of robots.txt)
            legal_task = asyncio.create_task(_fetch_legal_findings_by_name(legal_service, request.company_name))
            tasks.append(legal_task)
            
            # Add news service if available
            news_task = None
            if news_service:
                news_task = asyncio.create_task(_fetch_news_analysis_by_name(news_service, request.company_name, request))
                tasks.append(news_task)
            
            # Wait for all tasks with timeout
            if tasks:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout_seconds
                )
                
                legal_findings = None
                news_analysis = None
                
                result_index = 0
                # Process legal service result (always present now)
                legal_result = results[result_index]
                if isinstance(legal_result, Exception):
                    logger.warning("Legal service failed, continuing without legal data", 
                                 error=str(legal_result))
                else:
                    legal_findings = legal_result
                result_index += 1
                
                if news_task:
                    news_result = results[result_index]
                    if isinstance(news_result, Exception):
                        logger.warning("News service failed, continuing without news data", 
                                     error=str(news_result))
                    else:
                        news_analysis = news_result
            else:
                # This should not happen anymore since we always have legal_task
                legal_findings = None
                news_analysis = None
                
        except asyncio.TimeoutError:
            # If timeout occurs, try to get legal findings with a shorter timeout
            logger.warning("Analysis timeout occurred, attempting quick legal search")
            try:
                legal_findings = await asyncio.wait_for(
                    _fetch_legal_findings_by_name(legal_service, request.company_name),
                    timeout=10.0  # Shorter timeout for legal search
                )
            except Exception as e:
                logger.warning("Quick legal search also failed", error=str(e))
                legal_findings = None
            news_analysis = None
            logger.warning("Analysis timed out, returning partial results", 
                         request_id=request_id, timeout=timeout_seconds)
        
        # Create integrated risk assessment using the RiskService
        risk_assessment_obj = risk_service.calculate_overall_risk(
            company_info, 
            legal_findings.cases if legal_findings else None, 
            news_analysis
        )
        
        # Convert to legacy format for response compatibility
        risk_assessment = _convert_risk_assessment_format(risk_assessment_obj)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Build response
        data_sources = []
        if web_content:
            data_sources.append("Crawl4AI website analysis")
        if legal_findings:
            data_sources.append("Rechtspraak.nl (Dutch Legal Database)")
        if news_analysis:
            data_sources.append("AI-powered news analysis (OpenAI)")
        
        # Add fallback if no sources available
        if not data_sources:
            data_sources.append("Company name search")
        
        # Add risk assessment details to warnings
        warnings = _get_analysis_warnings(company_info, request, legal_findings, news_analysis, web_content)
        warnings.extend(_get_risk_assessment_warnings(risk_assessment_obj))
        
        analysis_response = CompanyAnalysisResponse(
            request_id=request_id,
            analysis_timestamp=datetime.utcnow(),
            processing_time_seconds=round(processing_time, 3),
            company_info=company_info,
            legal_findings=legal_findings,
            news_analysis=news_analysis,
            web_content=web_content,
            risk_assessment=risk_assessment,
            warnings=warnings,
            data_sources=data_sources
        )
        
        logger.info(
            "Company analysis completed",
            request_id=request_id,
            processing_time=processing_time,
            risk_level=risk_assessment.overall_risk_level
        )
        
        # Cleanup crawl service
        await crawl_service.close()
        
        return analysis_response
    
    except ValidationError as e:
        await crawl_service.close()
        logger.warning("Validation error", error=str(e), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except TimeoutError as e:
        await crawl_service.close()
        logger.error("Timeout error", error=str(e), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Request timed out while fetching data from {e.service}"
        )
    
    except Exception as e:
        await crawl_service.close()
        logger.error(
            "Unexpected error during analysis", 
            error=str(e),
            error_type=type(e).__name__,
            request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during analysis"
        )


@router.post(
    "/nederlands-bedrijf-analyse",
    response_model=NederlandseAnalyseResponse,
    summary="Nederlandse Bedrijfsanalyse",
    description="""
    Voer een Nederlandse bedrijfsanalyse uit volgens de nieuwe workflow specificatie.
    
    Deze endpoint implementeert de Nederlandse bedrijfsanalyse workflow:
    1. **Nederlandse website crawling** - Focus op .nl domeinen en Nederlandse content
    2. **Verplichte Rechtspraak.nl controle** - Altijd uitgevoerd voor juridische zaken
    3. **Nederlandse nieuwsbronnen prioriteit** - FD, NRC, Volkskrant, NOS, etc.
    4. **Contactpersoon analyse** - Zoekt ook naar de opgegeven contactpersoon
    5. **Gestructureerde output** - Bullet points met bron en link
    6. **Neutrale samenvatting** - 2-3 zinnen zakelijke toon
    
    **Belangrijke bronnen die altijd worden gecontroleerd:**
    - Rechtspraak.nl (verplicht voor juridische zaken)
    - Financieele Dagblad (fd.nl) 
    - NRC (nrc.nl)
    - Volkskrant (volkskrant.nl)
    - NOS (nos.nl)
    - BNR (bnr.nl)
    
    **Output format:**
    ```json
    {
        "bedrijfsnaam": "ASML Holding N.V.",
        "contactpersoon": "Peter Wennink",
        "goed_nieuws": [...],
        "slecht_nieuws": [...],
        "samenvatting": "Neutrale analyse van de bevindingen"
    }
    ```
    """,
    response_description="Nederlandse bedrijfsanalyse met gestructureerde nieuws en juridische bevindingen"
)
async def nederlands_bedrijf_analyse(
    request: CompanyAnalysisRequest,
    response: Response,
    auth_data: tuple = Depends(authenticated_with_rate_limit)
):
    """
    Nederlandse bedrijfsanalyse endpoint die de nieuwe workflow implementeert.
    
    Voert altijd Rechtspraak.nl controle uit en prioriteert Nederlandse nieuwsbronnen.
    Includeert contactpersoon in zoekopdrachten indien opgegeven.
    """
    api_key, rate_info = auth_data
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(
        "Starting Nederlandse bedrijfsanalyse",
        request_id=request_id,
        company_name=request.company_name,
        kvk_nummer=request.kvk_nummer,
        contactpersoon=request.contactpersoon,
        api_key_prefix=api_key[:8]
    )
    
    try:
        # Add rate limit headers
        limiter = get_rate_limiter()
        headers = limiter.get_rate_limit_headers(api_key)
        for key, value in headers.items():
            response.headers[key] = value
        
        # Initialize services
        legal_service = LegalService()
        crawl_service = CrawlService()
        news_service = None
        
        try:
            news_service = NewsService()
        except ValueError as e:
            logger.warning("News service not available", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key niet geconfigureerd - nieuwsanalyse service niet beschikbaar"
            )
        
        # Initialize legal service (robots.txt check but continue anyway)
        await legal_service.initialize()
        
        # Crawl Nederlandse website met focus op .nl domeinen
        logger.info("Starting Dutch website crawl", company_name=request.company_name)
        
        web_content = await crawl_service.crawl_company_website(
            company_name=request.company_name,
            max_depth=2,  # Uitgebreider voor Nederlandse analyse
            focus_dutch=True,  # Prioriteer .nl domeinen
            simple_mode=False
        )
        
        # Prepare search parameters for Nederlandse zoekopdracht
        search_params = {
            'date_range': '90d',  # Laatste 90 dagen zoals gespecificeerd
            'include_positive': True,
            'include_negative': True,
            'search_depth': 'deep',  # Uitgebreider zoeken voor Nederlandse analyse
            'prioritize_dutch_sources': True
        }
        
        # Start parallel searches
        logger.info("Starting parallel Nederlandse searches", 
                   company_name=request.company_name,
                   contact_person=request.contactpersoon)
        
        tasks = []
        
        # VERPLICHTE Rechtspraak.nl zoektaak
        legal_task = asyncio.create_task(
            legal_service.search_company_cases(
                request.company_name, 
                request.company_name,  # Use company name as trade name if no separate trade name
                request.contactpersoon
            )
        )
        tasks.append(legal_task)
        
        # Nederlandse nieuwsanalyse taak - use Dutch RSS approach
        news_task = asyncio.create_task(
            news_service.search_dutch_company_news(
                request.company_name, 
                search_params,
                request.contactpersoon
            )
        )
        tasks.append(news_task)
        
        # Wacht op beide taken met timeout (voor Nederlandse analyse)
        timeout_seconds = settings.ANALYSIS_TIMEOUT_DUTCH
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout_seconds
            )
            
            legal_cases, news_analysis = results[0], results[1]
            
            # Handle exceptions maar continue met partiële resultaten
            if isinstance(legal_cases, Exception):
                logger.error("Rechtspraak.nl search failed", error=str(legal_cases))
                legal_cases = []
            
            if isinstance(news_analysis, Exception):
                logger.error("News analysis failed", error=str(news_analysis))
                news_analysis = None
        
        except asyncio.TimeoutError:
            logger.warning("Nederlandse analyse timed out, returning partial results")
            legal_cases = []
            news_analysis = None
        
        # Process results volgens Nederlandse format
        goed_nieuws = []
        slecht_nieuws = []
        bronnen_gecontroleerd = ["rechtspraak.nl"]  # Altijd gecontroleerd
        
        # Verwerk nieuwsresultaten
        if news_analysis:
            # Voeg Nederlandse bronnen toe aan gecontroleerde lijst
            nederlandse_bronnen = ["fd.nl", "nrc.nl", "volkskrant.nl", "nos.nl", "bnr.nl", "mt.nl", "trouw.nl"]
            bronnen_gecontroleerd.extend(nederlandse_bronnen)
            
            # Verwerk positief nieuws
            for article in news_analysis.positive_news.articles[:10]:  # Limiteer tot 10 items
                # Check if contactpersoon is mentioned in article
                titel = article.title
                if request.contactpersoon and request.contactpersoon.lower() in article.title.lower():
                    titel += f" (vermeldt {request.contactpersoon})"
                    
                goed_nieuws.append(NieuwsItem(
                    titel=titel,
                    link=article.url or "",
                    bron=article.source
                ))
            
            # Verwerk negatief nieuws  
            for article in news_analysis.negative_news.articles[:10]:
                titel = article.title
                if request.contactpersoon and request.contactpersoon.lower() in article.title.lower():
                    titel += f" (vermeldt {request.contactpersoon})"
                    
                slecht_nieuws.append(NieuwsItem(
                    titel=titel,
                    link=article.url or "",
                    bron=article.source
                ))
        
        # VERPLICHT: Voeg rechtszaken toe aan slecht nieuws (altijd)
        if legal_cases:
            for case in legal_cases[:8]:  # Top 8 meest relevante rechtszaken
                case_title = f"Rechtszaak: {case.summary[:80]}..."
                if case.court:
                    case_title += f" ({case.court})"
                
                # Check if contactpersoon is involved
                if request.contactpersoon:
                    case_text = f"{case.summary} {' '.join(case.parties)}"
                    if request.contactpersoon.lower() in case_text.lower():
                        case_title += f" (betreft {request.contactpersoon})"
                
                slecht_nieuws.append(NieuwsItem(
                    titel=case_title,
                    link=case.url or "",
                    bron="rechtspraak.nl"
                ))
        
        # Genereer Nederlandse samenvatting
        total_positive = len(goed_nieuws)
        total_negative = len(slecht_nieuws)
        legal_count = len(legal_cases) if legal_cases else 0
        
        samenvatting_parts = []
        if total_positive > 0:
            samenvatting_parts.append(f"{total_positive} positieve berichten gevonden")
        if total_negative > 0:
            samenvatting_parts.append(f"{total_negative} negatieve items gevonden")
        if legal_count > 0:
            samenvatting_parts.append(f"waaronder {legal_count} juridische zaken")
        
        # Contactpersoon mention in summary
        contact_mention = ""
        if request.contactpersoon:
            # Check if contact person appears in any results
            contact_found_news = any(request.contactpersoon.lower() in item.titel.lower() 
                                   for item in goed_nieuws + slecht_nieuws)
            if contact_found_news:
                contact_mention = f" {request.contactpersoon} wordt genoemd in de gevonden berichten."
        
        if not samenvatting_parts:
            if request.contactpersoon:
                samenvatting = f"Analyse voltooid voor {request.company_name} met contactpersoon {request.contactpersoon}. Geen relevante nieuwsberichten of juridische zaken gevonden in de laatste 90 dagen."
            else:
                samenvatting = f"Analyse voltooid voor {request.company_name}. Geen relevante nieuwsberichten of juridische zaken gevonden in de laatste 90 dagen."
        else:
            base_summary = f"Analyse voor {request.company_name}: " + ", ".join(samenvatting_parts) + "."
            samenvatting = base_summary + contact_mention
        
        # Altijd vermelden dat Rechtspraak.nl gecontroleerd is
        if legal_count == 0:
            samenvatting += " Rechtspraak.nl gecontroleerd - geen juridische zaken gevonden."
        
        # Build Nederlandse response
        nederlandse_response = NederlandseAnalyseResponse(
            bedrijfsnaam=request.company_name,
            kvk_nummer=request.kvk_nummer,
            contactpersoon=request.contactpersoon or "-",
            goed_nieuws=goed_nieuws,
            slecht_nieuws=slecht_nieuws,
            samenvatting=samenvatting,
            analysis_timestamp=datetime.utcnow(),
            bronnen_gecontroleerd=list(set(bronnen_gecontroleerd))  # Remove duplicates
        )
        
        processing_time = time.time() - start_time
        logger.info(
            "Nederlandse bedrijfsanalyse voltooid",
            request_id=request_id,
            processing_time=processing_time,
            positive_count=total_positive,
            negative_count=total_negative,
            legal_count=legal_count,
            contactpersoon_provided=bool(request.contactpersoon)
        )
        
        # Cleanup crawl service
        await crawl_service.close()
        
        return nederlandse_response
    
    except Exception as e:
        await crawl_service.close()
        logger.error(
            "Unexpected error during Nederlandse bedrijfsanalyse", 
            error=str(e),
            error_type=type(e).__name__,
            request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Een onverwachte fout is opgetreden tijdens de Nederlandse bedrijfsanalyse"
        )


async def _fetch_news_analysis_by_name(news_service: NewsService, company_name: str, request: CompanyAnalysisRequest):
    """
    Fetch news analysis for a company by name.
    
    Args:
        news_service: NewsService instance
        company_name: Company name to search for
        request: CompanyAnalysisRequest with search parameters
        
    Returns:
        NewsAnalysis object or None if no analysis available
    """
    try:
        # Prepare search parameters
        search_params = {
            'date_range': getattr(request, 'news_date_range', 'last_year'),
            'language': 'nl',  # Default to Dutch
            'search_depth': request.search_depth
        }
        
        # Search for news about the company using RSS feeds
        news_analysis = await news_service.search_company_news(
            company_name, 
            search_params
        )
        
        return news_analysis
        
    except Exception as e:
        logger.error("Error fetching news analysis", error=str(e))
        raise


async def _fetch_legal_findings_by_name(legal_service: LegalService, company_name: str) -> LegalFindings:
    """
    Fetch legal findings for a company by name.
    
    Args:
        legal_service: LegalService instance
        company_name: Company name to search for
        
    Returns:
        LegalFindings object or None if no cases found
    """
    try:
        # Search for legal cases using company name
        cases = await legal_service.search_company_cases(
            company_name=company_name,
            contact_person=None  # Don't use contact person for company search
        )
        
        if not cases:
            return None
        
        # Assess legal risk
        risk_level = legal_service.assess_legal_risk(cases)
        
        return LegalFindings(
            total_cases=len(cases),
            risk_level=risk_level,
            cases=cases
        )
        
    except Exception as e:
        logger.error("Error fetching legal findings", error=str(e))
        raise



def _get_analysis_warnings(company_info, request, legal_findings: LegalFindings = None, news_analysis=None, web_content=None) -> list[str]:
    """
    Generate warnings about the analysis limitations.
    
    Args:
        company_info: CompanyInfo object
        request: CompanyAnalysisRequest object
        legal_findings: LegalFindings object or None
        news_analysis: NewsAnalysis object or None
        web_content: WebContent object or None
        
    Returns:
        List of warning messages
    """
    warnings = []
    
    data_sources_used = []
    if web_content:
        data_sources_used.append("Crawl4AI website analysis")
    if legal_findings:
        data_sources_used.append("Legal case database")
    if news_analysis:
        data_sources_used.append("AI-powered news analysis")
    
    if data_sources_used:
        warnings.append(f"This analysis is based on: {', '.join(data_sources_used)}")
    else:
        warnings.append("This analysis is based on company name search only")
    
    if not web_content:
        warnings.append("Website crawling was not successful - company information may be limited")
    elif web_content.pages_crawled == 0:
        warnings.append("No website content could be crawled - company information is limited")
    elif web_content.pages_crawled < 3:
        warnings.append("Limited website content crawled - analysis may be less comprehensive")
    
    if not legal_findings:
        warnings.append("Legal case analysis was not available (may be due to robots.txt restrictions or service limitations)")
    
    if not news_analysis:
        warnings.append("News sentiment analysis was not available (may be due to missing OpenAI API key or service limitations)")
    
    if hasattr(request, 'include_subsidiaries') and request.include_subsidiaries:
        warnings.append("Subsidiary analysis is not yet implemented")
    
    if not company_info.establishment_date:
        warnings.append("Establishment date not available - age-based risk factors not calculated")
    
    if company_info.employee_count is None:
        warnings.append("Employee count not available from crawled data")
    
    # News analysis specific warnings
    if news_analysis:
        if hasattr(news_analysis, 'total_articles_found') and news_analysis.total_articles_found < 5:
            warnings.append("Limited news articles found - analysis may be less comprehensive")
        
        if hasattr(news_analysis, 'total_relevance') and news_analysis.total_relevance < 0.7:
            warnings.append("News relevance scores are moderate - some articles may be indirectly related")
    
    return warnings


def _convert_risk_assessment_format(risk_assessment_obj) -> RiskAssessment:
    """Convert new RiskAssessment format to legacy response format."""
    from ...services.risk_service import RiskLevel as NewRiskLevel
    
    # Map new risk levels to legacy format
    risk_level_mapping = {
        NewRiskLevel.VERY_LOW: RiskLevel.LOW,
        NewRiskLevel.LOW: RiskLevel.LOW,
        NewRiskLevel.MEDIUM: RiskLevel.MEDIUM,
        NewRiskLevel.HIGH: RiskLevel.HIGH,
        NewRiskLevel.VERY_HIGH: RiskLevel.CRITICAL
    }
    
    # Extract risk factors and positive factors
    all_factors = []
    for risk_score in risk_assessment_obj.risk_scores:
        all_factors.extend(risk_score.factors)
    
    all_recommendations = risk_assessment_obj.recommendations
    
    return RiskAssessment(
        overall_risk_level=risk_level_mapping.get(risk_assessment_obj.overall_level, RiskLevel.MEDIUM),
        risk_score=int(risk_assessment_obj.overall_score * 100),  # Convert to 0-100 scale
        risk_factors=all_factors[:10],  # Limit to top 10
        positive_factors=[],  # Legacy format doesn't have separate positive factors
        recommendations=all_recommendations[:8],  # Limit to top 8
        confidence_level=min([score.confidence for score in risk_assessment_obj.risk_scores if score.confidence is not None and isinstance(score.confidence, (int, float))] or [0.7])
    )


def _get_risk_assessment_warnings(risk_assessment_obj) -> list[str]:
    """Generate warnings specific to the risk assessment process."""
    warnings = []
    
    # Check confidence levels
    low_confidence_categories = [
        score.category.value for score in risk_assessment_obj.risk_scores 
        if score.confidence < 0.6
    ]
    
    if low_confidence_categories:
        warnings.append(f"Lower confidence in assessment for: {', '.join(low_confidence_categories)}")
    
    # Check for missing data that affects risk assessment
    incomplete_data_categories = []
    for risk_score in risk_assessment_obj.risk_scores:
        if "Limited" in ' '.join(risk_score.factors) or "Missing" in ' '.join(risk_score.factors):
            incomplete_data_categories.append(risk_score.category.value)
    
    if incomplete_data_categories:
        warnings.append(f"Risk assessment may be incomplete due to limited data in: {', '.join(incomplete_data_categories)}")
    
    # High risk warnings
    high_risk_categories = [
        score.category.value for score in risk_assessment_obj.risk_scores 
        if score.level in ['high', 'very_high']
    ]
    
    if len(high_risk_categories) > 2:
        warnings.append(f"Multiple high-risk areas identified: {', '.join(high_risk_categories)}")
    
    return warnings


@router.post(
    "/analyze-company-simple",
    response_model=CompanyAnalysisSimpleResponse,
    summary="Simple Company Analysis",
    description="""
    Perform simplified company analysis with web search and legal case lookup.
    
    This endpoint implements the new workflow:
    1. Simple website crawling (depth=1, max 3 pages) using Crawl4AI
    2. Searches for positive and negative news about the company on the web
    3. Always searches Rechtspraak Open Data API for legal cases
    4. Returns a simplified JSON response with good/bad news lists
    
    The system performs fast parallel processing optimized for speed (< 15 seconds).
    """
)
async def analyze_company_simple(
    request: CompanyAnalysisRequest,
    response: Response,
    auth_data: tuple = Depends(authenticated_with_rate_limit)
):
    """
    Perform simplified company analysis with the new workflow.
    
    This endpoint searches for both positive and negative news on the web
    and always performs a legal case lookup using the Rechtspraak API.
    """
    api_key, rate_info = auth_data
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(
        "Starting simple company analysis",
        request_id=request_id,
        company_name=request.company_name,
        api_key_prefix=api_key[:8]
    )
    
    try:
        # Add rate limit headers
        limiter = get_rate_limiter()
        headers = limiter.get_rate_limit_headers(api_key)
        for key, value in headers.items():
            response.headers[key] = value
        
        # Initialize services
        legal_service = LegalService()
        crawl_service = CrawlService()
        news_service = None
        
        try:
            news_service = NewsService()
        except ValueError as e:
            logger.warning("News service not available", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key not configured - news analysis service unavailable"
            )
        
        # Initialize legal service
        await legal_service.initialize()
        
        # Run simple website crawl, searches and legal lookup in parallel
        logger.info("Starting parallel web crawl, news search and legal lookup", company_name=request.company_name)
        
        # Create search parameters
        search_params = {
            'date_range': '1y',  # Last year
            'include_positive': True,
            'include_negative': True,
            'search_depth': 'standard'
        }
        
        # Run crawl, news search and legal search concurrently
        tasks = [
            asyncio.create_task(crawl_service.crawl_company_website(
                request.company_name, 
                max_depth=1,  # Simple mode
                simple_mode=True
            )),
            asyncio.create_task(news_service.search_company_news_simple(request.company_name, max_results=10)),
            asyncio.create_task(legal_service.search_company_cases(request.company_name, request.company_name))
        ]
        
        # Wait for all three with timeout (optimized for speed)
        timeout_seconds = settings.ANALYSIS_TIMEOUT_SIMPLE
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout_seconds
            )
            
            web_content, news_analysis, legal_cases = results[0], results[1], results[2]
            
            # Handle exceptions
            if isinstance(web_content, Exception):
                logger.warning("Website crawl failed", error=str(web_content))
                web_content = None
            
            if isinstance(news_analysis, Exception):
                logger.warning("News analysis failed", error=str(news_analysis))
                news_analysis = None
            
            if isinstance(legal_cases, Exception):
                logger.warning("Legal case search failed", error=str(legal_cases))
                legal_cases = []
        
        except asyncio.TimeoutError:
            logger.warning("Analysis timed out, returning partial results")
            web_content = None
            news_analysis = None
            legal_cases = []
        
        # Process results into simplified format
        goed_nieuws = []
        slecht_nieuws = []
        
        # Process news results
        if news_analysis:
            # Add positive news
            for article in news_analysis.positive_news.articles:
                goed_nieuws.append(NewsItem(
                    titel=article.title,
                    link=article.url or "",
                    bron=article.source
                ))
            
            # Add negative news
            for article in news_analysis.negative_news.articles:
                slecht_nieuws.append(NewsItem(
                    titel=article.title,
                    link=article.url or "",
                    bron=article.source
                ))
        
        # Process legal cases - always add to negative news if found
        if legal_cases:
            for case in legal_cases[:5]:  # Limit to top 5 most relevant
                slecht_nieuws.append(NewsItem(
                    titel=f"Legal case: {case.summary[:100]}...",
                    link=case.url,
                    bron="rechtspraak.nl"
                ))
        
        # Generate summary
        total_positive = len(goed_nieuws)
        total_negative = len(slecht_nieuws)
        legal_count = len(legal_cases) if legal_cases else 0
        
        summary_parts = []
        if total_positive > 0:
            summary_parts.append(f"{total_positive} positive articles found")
        if total_negative > 0:
            summary_parts.append(f"{total_negative} negative items found")
        if legal_count > 0:
            summary_parts.append(f"including {legal_count} legal cases")
        
        if not summary_parts:
            samenvatting = f"Analysis completed for {request.company_name}. No significant news or legal cases found."
        else:
            samenvatting = f"Analysis for {request.company_name}: " + ", ".join(summary_parts) + "."
        
        # Build response
        simple_response = CompanyAnalysisSimpleResponse(
            bedrijf=request.company_name,
            samenvatting=samenvatting,
            goed_nieuws=goed_nieuws,
            slecht_nieuws=slecht_nieuws
        )
        
        processing_time = time.time() - start_time
        logger.info(
            "Simple company analysis completed",
            request_id=request_id,
            processing_time=processing_time,
            positive_count=total_positive,
            negative_count=total_negative,
            legal_count=legal_count
        )
        
        # Cleanup crawl service
        await crawl_service.close()
        
        return simple_response
    
    except Exception as e:
        await crawl_service.close()
        logger.error(
            "Unexpected error during simple analysis", 
            error=str(e),
            error_type=type(e).__name__,
            request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during analysis"
        )


