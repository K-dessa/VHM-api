import time
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
import structlog

from ...api.dependencies import authenticated_with_rate_limit
from ...core.config import settings
from ...models.request_models import CompanyAnalysisRequest
from ...models.response_models import LegalFindings
from ...services.legal_service import LegalService
from ...utils.rate_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/LegalSearch",
    response_model=LegalFindings,
    summary="Zoek juridische zaken op Rechtspraak.nl",
    description="""
    Voert een gerichte zoekopdracht uit op Rechtspraak.nl voor het opgegeven bedrijf.
    Optioneel kan een contactpersoon worden meegegeven. Deze route zoekt uitsluitend
    naar rechtszaken (geen nieuws) en retourneert alleen resultaten van Rechtspraak.nl.
    """,
    response_description="Overzicht met relevante zaken en risiconiveau"
)
async def legal_search(
    request: CompanyAnalysisRequest,
    response: Response,
    auth_data: tuple = Depends(authenticated_with_rate_limit)
):
    """Legal-only zoekroute die uitsluitend Rechtspraak.nl bevraagt."""
    api_key, _rate_info = auth_data
    request_id = str(uuid.uuid4())
    start_time = time.time()

    logger.info(
        "Starting LegalSearch",
        request_id=request_id,
        company_name=request.company_name,
        contactpersoon=getattr(request, "contactpersoon", None),
    )

    # Rate limit headers
    limiter = get_rate_limiter()
    headers = limiter.get_rate_limit_headers(api_key)
    for key, value in headers.items():
        response.headers[key] = value

    try:
        # Initialize legal service
        legal_service = LegalService()
        await legal_service.initialize()

        # Perform Rechtspraak-only search
        cases = await legal_service.search_company_cases(
            request.company_name,
            request.company_name,  # trade name fallback
            getattr(request, "contactpersoon", None),
        )

        risk_level = legal_service.assess_legal_risk(cases)

        processing_time = time.time() - start_time
        logger.info(
            "LegalSearch completed",
            request_id=request_id,
            processing_time=processing_time,
            total_cases=len(cases),
            risk_level=risk_level,
        )

        return LegalFindings(
            total_cases=len(cases),
            risk_level=risk_level,
            cases=cases,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Unexpected error during LegalSearch",
            error=str(e),
            error_type=type(e).__name__,
            request_id=request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Er is een onverwachte fout opgetreden tijdens LegalSearch",
        )

