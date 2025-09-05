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
    
    This endpoint integrates multiple data sources to provide a complete company analysis:
    - **Legal risk assessment** from court case database analysis
    - **News sentiment analysis** using AI-powered processing (OpenAI GPT-4)
    - **Integrated risk scoring** combining all factors
    
    The analysis includes legal, operational, and reputational risk factors
    with actionable recommendations and monitoring suggestions.
    
    **Note**: This service requires an OpenAI API key to be configured.
    """,
    response_description="""
    Complete analysis results including:
    - Company information from official sources
    - Legal findings and risk assessment
    - News analysis with sentiment scoring
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
        
        # Initialize services (no KvK service needed)
        legal_service = LegalService()
        risk_service = RiskService()
        
        # Initialize news service if OpenAI API key is available
        news_service = None
        try:
            news_service = NewsService()
        except ValueError as e:
            logger.warning("News service not available", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key not configured - news analysis service unavailable"
            )
        
        # Initialize legal service (robots.txt check)
        await legal_service.initialize()
        
        # Create basic company info from the provided name
        company_info = CompanyInfo(
            name=request.company_name,
            trade_name=None,
            legal_form=None,
            establishment_date=None,
            address=None,
            sbi_codes=[],
            business_activities=[],
            employee_count=None,
            website=None,
            email=None,
            phone=None,
            status="Unknown"
        )
        
        # Fetch legal cases and news analysis in parallel
        logger.info("Fetching legal cases and news analysis", company_name=request.company_name)
        
        # Set timeout based on search depth
        timeout_seconds = 30 if request.search_depth == "standard" else 60
        
        try:
            # Run legal and news services in parallel with timeout
            tasks = []
            
            # Add legal service if allowed by robots.txt
            legal_task = None
            if legal_service.robots_allowed:
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
                if legal_task:
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
                legal_findings = None
                news_analysis = None
                
        except asyncio.TimeoutError:
            # If timeout occurs, continue with basic info
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
        if legal_findings:
            data_sources.append("Rechtspraak.nl (Dutch Legal Database)")
        if news_analysis:
            data_sources.append("AI-powered news analysis (OpenAI)")
        
        # Add basic info source
        data_sources.insert(0, "Company name search")
        
        # Add risk assessment details to warnings
        warnings = _get_analysis_warnings(company_info, request, legal_findings, news_analysis)
        warnings.extend(_get_risk_assessment_warnings(risk_assessment_obj))
        
        analysis_response = CompanyAnalysisResponse(
            request_id=request_id,
            analysis_timestamp=datetime.utcnow(),
            processing_time_seconds=round(processing_time, 3),
            company_info=company_info,
            legal_findings=legal_findings,
            news_analysis=news_analysis,
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
        
        return analysis_response
    
    except ValidationError as e:
        logger.warning("Validation error", error=str(e), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except TimeoutError as e:
        logger.error("Timeout error", error=str(e), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Request timed out while fetching data from {e.service}"
        )
    
    except Exception as e:
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
    1. **Verplichte Rechtspraak.nl controle** - Altijd uitgevoerd voor juridische zaken
    2. **Nederlandse nieuwsbronnen prioriteit** - FD, NRC, Volkskrant, NOS, etc.
    3. **Contactpersoon analyse** - Zoekt ook naar de opgegeven contactpersoon
    4. **Gestructureerde output** - Bullet points met bron en link
    5. **Neutrale samenvatting** - 2-3 zinnen zakelijke toon
    
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
        
        # Nederlandse nieuwsanalyse taak
        news_task = asyncio.create_task(
            news_service.search_company_news(
                request.company_name, 
                search_params,
                request.contactpersoon
            )
        )
        tasks.append(news_task)
        
        # Wacht op beide taken met timeout (90 sec voor grondige Nederlandse analyse)
        timeout_seconds = 90
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
        
        return nederlandse_response
    
    except Exception as e:
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
        
        # Search for news about the company
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
            company_name, 
            company_name  # Use same name for both official and trade name
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


async def _fetch_news_analysis(news_service: NewsService, company_task, request: CompanyAnalysisRequest):
    """
    Fetch news analysis for a company.
    
    Args:
        news_service: NewsService instance
        company_task: Asyncio task that will provide company info
        request: CompanyAnalysisRequest with search parameters
        
    Returns:
        NewsAnalysis object or None if no analysis available
    """
    try:
        # Wait for company info to be available
        company_info = await company_task
        
        # Prepare search parameters
        search_params = {
            'date_range': getattr(request, 'date_range', '6m'),
            'include_positive': getattr(request, 'include_positive', True),
            'include_negative': getattr(request, 'include_negative', True),
            'language': 'nl',  # Default to Dutch
            'search_depth': request.search_depth
        }
        
        # Search for news about the company
        news_analysis = await news_service.search_company_news(
            company_info.name, 
            search_params
        )
        
        return news_analysis
        
    except Exception as e:
        logger.error("Error fetching news analysis", error=str(e))
        raise


async def _fetch_legal_findings(legal_service: LegalService, company_task) -> LegalFindings:
    """
    Fetch legal findings for a company.
    
    Args:
        legal_service: LegalService instance
        company_task: Asyncio task that will provide company info
        
    Returns:
        LegalFindings object or None if no cases found
    """
    try:
        # Wait for company info to be available
        company_info = await company_task
        
        # Search for legal cases
        cases = await legal_service.search_company_cases(
            company_info.name, 
            company_info.trade_name
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


def _create_comprehensive_risk_assessment(company_info, legal_findings: LegalFindings = None, news_analysis=None) -> RiskAssessment:
    """
    Create a comprehensive risk assessment based on company, legal, and news information.
    
    Args:
        company_info: CompanyInfo object from KvK
        legal_findings: LegalFindings object or None
        news_analysis: NewsAnalysis object or None
        
    Returns:
        RiskAssessment object
    """
    risk_factors = []
    positive_factors = []
    risk_score = 20  # Base score (low risk)
    
    # Check company status
    if company_info.status.lower() not in ['active', 'actief']:
        risk_factors.append(f"Company status is '{company_info.status}'")
        risk_score += 30
    else:
        positive_factors.append("Company has active status")
    
    # Check establishment date
    if company_info.establishment_date:
        years_active = (datetime.now() - company_info.establishment_date).days / 365.25
        if years_active < 1:
            risk_factors.append("Company is less than 1 year old")
            risk_score += 15
        elif years_active > 10:
            positive_factors.append(f"Company has been active for {int(years_active)} years")
            risk_score -= 5
    
    # Check if company has trade name
    if company_info.trade_name and company_info.trade_name != company_info.name:
        positive_factors.append("Company has established trade name")
    
    # Check employee count
    if company_info.employee_count is not None:
        if company_info.employee_count == 0:
            risk_factors.append("No employees reported")
            risk_score += 10
        elif company_info.employee_count > 50:
            positive_factors.append(f"Substantial workforce ({company_info.employee_count} employees)")
            risk_score -= 5
    
    # Check business activities
    if not company_info.sbi_codes:
        risk_factors.append("No business activities (SBI codes) reported")
        risk_score += 10
    elif len(company_info.sbi_codes) > 5:
        risk_factors.append("Very diverse business activities (potential unclear focus)")
        risk_score += 5
    
    # Check website presence
    if company_info.website:
        positive_factors.append("Company has online presence (website)")
        risk_score -= 3
    
    # Incorporate legal findings if available
    if legal_findings:
        legal_risk_level = legal_findings.risk_level.lower()
        case_count = legal_findings.total_cases
        
        if legal_risk_level == 'high':
            risk_factors.append(f"High legal risk identified ({case_count} legal cases found)")
            risk_score += 25
        elif legal_risk_level == 'medium':
            risk_factors.append(f"Medium legal risk identified ({case_count} legal cases found)")
            risk_score += 15
        elif legal_risk_level == 'low' and case_count > 0:
            risk_factors.append(f"Some legal cases found ({case_count} cases)")
            risk_score += 5
        
        # Check for criminal cases specifically
        criminal_cases = sum(1 for case in legal_findings.cases if case.type == 'criminal')
        if criminal_cases > 0:
            risk_factors.append(f"Criminal cases found ({criminal_cases} cases)")
            risk_score += 15
        
        # Check for recent cases (within 2 years)
        from datetime import timedelta
        recent_threshold = datetime.now() - timedelta(days=730)
        recent_cases = sum(1 for case in legal_findings.cases if case.date > recent_threshold)
        if recent_cases > 0:
            risk_factors.append(f"Recent legal activity ({recent_cases} cases within 2 years)")
            risk_score += 8
    else:
        # No legal data available - note this limitation
        positive_factors.append("No adverse legal cases found in public records")
    
    # Incorporate news analysis if available
    if news_analysis:
        overall_sentiment = news_analysis.overall_sentiment
        negative_count = news_analysis.negative_news.count
        positive_count = news_analysis.positive_news.count
        
        # Sentiment-based risk adjustment
        if overall_sentiment < -0.3:
            risk_factors.append(f"Negative media sentiment detected (score: {overall_sentiment:.2f})")
            risk_score += 15
        elif overall_sentiment < -0.1:
            risk_factors.append(f"Mildly negative media sentiment (score: {overall_sentiment:.2f})")
            risk_score += 8
        elif overall_sentiment > 0.3:
            positive_factors.append(f"Positive media sentiment (score: {overall_sentiment:.2f})")
            risk_score -= 5
        elif overall_sentiment > 0.1:
            positive_factors.append(f"Mildly positive media sentiment (score: {overall_sentiment:.2f})")
            risk_score -= 2
        
        # Risk indicators from news
        if news_analysis.risk_indicators:
            for indicator in news_analysis.risk_indicators:
                risk_factors.append(f"News risk indicator: {indicator}")
                risk_score += 8
        
        # Negative news impact
        if negative_count > 3:
            risk_factors.append(f"High volume of negative news coverage ({negative_count} articles)")
            risk_score += 12
        elif negative_count > 1:
            risk_factors.append(f"Some negative news coverage ({negative_count} articles)")
            risk_score += 5
        
        # Positive news benefit
        if positive_count > 2:
            positive_factors.append(f"Good positive news coverage ({positive_count} articles)")
            risk_score -= 3
        
        # Check for specific concerning topics
        if news_analysis.key_topics:
            concerning_topics = {'Legal Issues', 'Financial Concerns', 'Regulatory Issues', 'Reputation Risk'}
            found_concerns = set(news_analysis.key_topics).intersection(concerning_topics)
            if found_concerns:
                risk_factors.append(f"Concerning news topics: {', '.join(found_concerns)}")
                risk_score += len(found_concerns) * 5
    else:
        # No news analysis available - note this limitation
        positive_factors.append("No adverse news coverage detected in recent analysis")
    
    # Determine overall risk level
    risk_score = max(0, min(100, risk_score))  # Clamp between 0-100
    
    if risk_score < 25:
        risk_level = RiskLevel.LOW
    elif risk_score < 50:
        risk_level = RiskLevel.MEDIUM
    elif risk_score < 75:
        risk_level = RiskLevel.HIGH
    else:
        risk_level = RiskLevel.CRITICAL
    
    recommendations = []
    if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        recommendations.append("Conduct additional due diligence before business engagement")
        recommendations.append("Request recent financial statements and references")
        
        # Legal-specific recommendations
        if legal_findings and legal_findings.total_cases > 0:
            recommendations.append("Review legal case details and assess potential ongoing litigation risks")
            
            criminal_cases = sum(1 for case in legal_findings.cases if case.type == 'criminal')
            if criminal_cases > 0:
                recommendations.append("Exercise extreme caution due to criminal case history")
    
    if company_info.status.lower() not in ['active', 'actief']:
        recommendations.append("Verify current company status with KvK directly")
    
    if legal_findings and legal_findings.total_cases > 2:
        recommendations.append("Consider legal consultation before proceeding with significant business relationships")
    
    # Calculate confidence level based on available data sources
    confidence_level = 0.6  # Base confidence with KvK data
    if legal_findings:
        confidence_level += 0.15  # Increase confidence with legal data
        if legal_findings.total_cases > 0:
            confidence_level += 0.05  # Additional confidence if we found actual cases
    
    if news_analysis:
        confidence_level += 0.15  # Increase confidence with news data
        if news_analysis.total_articles_found > 5:
            confidence_level += 0.05  # Additional confidence with more articles
    
    confidence_level = min(1.0, confidence_level)  # Cap at 1.0
    
    return RiskAssessment(
        overall_risk_level=risk_level,
        risk_score=risk_score,
        risk_factors=risk_factors,
        positive_factors=positive_factors,
        recommendations=recommendations if recommendations else ["Standard business verification recommended"],
        confidence_level=confidence_level
    )


def _get_analysis_warnings(company_info, request, legal_findings: LegalFindings = None, news_analysis=None) -> list[str]:
    """
    Generate warnings about the analysis limitations.
    
    Args:
        company_info: CompanyInfo object
        request: CompanyAnalysisRequest object
        legal_findings: LegalFindings object or None
        news_analysis: NewsAnalysis object or None
        
    Returns:
        List of warning messages
    """
    warnings = []
    
    data_sources_used = ["KvK (Chamber of Commerce)"]
    if legal_findings:
        data_sources_used.append("Legal case database")
    if news_analysis:
        data_sources_used.append("AI-powered news analysis")
    
    warnings.append(f"This analysis is based on: {', '.join(data_sources_used)}")
    
    if not legal_findings:
        warnings.append("Legal case analysis was not available (may be due to robots.txt restrictions or service limitations)")
    
    if not news_analysis:
        warnings.append("News sentiment analysis was not available (may be due to missing OpenAI API key or service limitations)")
    
    if request.include_subsidiaries:
        warnings.append("Subsidiary analysis is not yet implemented")
    
    if not company_info.establishment_date:
        warnings.append("Establishment date not available - age-based risk factors not calculated")
    
    if company_info.employee_count is None:
        warnings.append("Employee count not available from KvK data")
    
    # News analysis specific warnings
    if news_analysis:
        if news_analysis.total_articles_found < 5:
            warnings.append("Limited news articles found - analysis may be less comprehensive")
        
        if news_analysis.total_relevance < 0.7:
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
        confidence_level=min([score.confidence for score in risk_assessment_obj.risk_scores if score.confidence is not None] + [0.7])
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
    1. Searches for positive and negative news about the company on the web
    2. Always searches Rechtspraak Open Data API for legal cases
    3. Returns a simplified JSON response with good/bad news lists
    
    The system searches asynchronously and combines results from web and legal sources.
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
        
        # Run searches in parallel
        logger.info("Starting parallel web search and legal lookup", company_name=request.company_name)
        
        # Create search parameters
        search_params = {
            'date_range': '1y',  # Last year
            'include_positive': True,
            'include_negative': True,
            'search_depth': 'standard'
        }
        
        # Run both searches concurrently
        tasks = [
            asyncio.create_task(news_service.search_company_news(request.company_name, search_params)),
            asyncio.create_task(legal_service.search_company_cases(request.company_name, request.company_name))
        ]
        
        # Wait for both with timeout
        timeout_seconds = 60  # Allow more time for web searches
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout_seconds
            )
            
            news_analysis, legal_cases = results[0], results[1]
            
            # Handle exceptions
            if isinstance(news_analysis, Exception):
                logger.warning("News analysis failed", error=str(news_analysis))
                news_analysis = None
            
            if isinstance(legal_cases, Exception):
                logger.warning("Legal case search failed", error=str(legal_cases))
                legal_cases = []
        
        except asyncio.TimeoutError:
            logger.warning("Analysis timed out, returning partial results")
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
        
        return simple_response
    
    except Exception as e:
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


@router.post(
    "/nederlands-bedrijf-analyse",
    response_model=NederlandseAnalyseResponse,
    summary="Nederlandse Bedrijfsanalyse",
    description="""
    Voer een Nederlandse bedrijfsanalyse uit volgens de nieuwe workflow specificatie.
    
    Deze endpoint implementeert de Nederlandse bedrijfsanalyse workflow:
    1. **Verplichte Rechtspraak.nl controle** - Altijd uitgevoerd voor juridische zaken
    2. **Nederlandse nieuwsbronnen prioriteit** - FD, NRC, Volkskrant, NOS, etc.
    3. **Contactpersoon analyse** - Zoekt ook naar de opgegeven contactpersoon
    4. **Gestructureerde output** - Bullet points met bron en link
    5. **Neutrale samenvatting** - 2-3 zinnen zakelijke toon
    
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
        
        # Nederlandse nieuwsanalyse taak
        news_task = asyncio.create_task(
            news_service.search_company_news(
                request.company_name, 
                search_params,
                request.contactpersoon
            )
        )
        tasks.append(news_task)
        
        # Wacht op beide taken met timeout (90 sec voor grondige Nederlandse analyse)
        timeout_seconds = 90
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
        
        return nederlandse_response
    
    except Exception as e:
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
