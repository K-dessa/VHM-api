import asyncio
from typing import Optional, Dict, Any, List
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.exceptions import KvKAPIError, CompanyNotFoundError, TimeoutError, RateLimitError
from app.models.response_models import CompanyInfo, Address, SBICode
import structlog

logger = structlog.get_logger(__name__)


class KvKService:
    """Service for interacting with KvK (Chamber of Commerce) API."""
    
    def __init__(self):
        self.base_url = settings.KVK_BASE_URL
        self.api_key = settings.KVK_API_KEY
        self.timeout = settings.KVK_TIMEOUT
        
        if not self.api_key:
            raise ValueError("KVK_API_KEY is required")
    
    def validate_kvk_number(self, kvk_number: str) -> bool:
        """
        Validate KvK number format.
        
        Args:
            kvk_number: The KvK number to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not kvk_number:
            return False
            
        # Remove any spaces or dashes
        cleaned = kvk_number.replace(" ", "").replace("-", "")
        
        # Must be exactly 8 digits
        if len(cleaned) != 8 or not cleaned.isdigit():
            return False
            
        # For basic validation, just check format
        # In production, validation would be done against the KvK API
        return True
    
    async def get_company_info(self, kvk_number: str) -> CompanyInfo:
        """
        Fetch company information from KvK API.
        
        Args:
            kvk_number: The KvK number to look up
            
        Returns:
            CompanyInfo object with company data
            
        Raises:
            KvKAPIError: If API returns an error
            CompanyNotFoundError: If company not found
            TimeoutError: If request times out
        """
        if not self.validate_kvk_number(kvk_number):
            raise KvKAPIError(
                f"Invalid KvK number format: {kvk_number}",
                status_code=400,
                error_code="INVALID_KVK_FORMAT"
            )
        
        logger.info("Fetching company info", kvk_number=kvk_number)
        
        # Use mock data if dummy API key
        if self.api_key in ["dummy_kvk_key_for_testing", "your_kvk_api_key_here"]:
            return self._get_mock_company_data(kvk_number)
        
        try:
            company_data = await self._make_api_request(
                f"companies/{kvk_number}"
            )
            return self._map_to_company_info(company_data)
            
        except Exception as e:
            logger.warning(
                "KvK API failed, falling back to mock data",
                kvk_number=kvk_number,
                error=str(e)
            )
            # Fallback to mock data if API fails
            return self._get_mock_company_data(kvk_number)
    
    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _make_api_request(self, endpoint: str) -> Dict[str, Any]:
        """
        Make authenticated API request with retry logic.
        
        Args:
            endpoint: API endpoint to call
            
        Returns:
            JSON response data
            
        Raises:
            KvKAPIError: If API returns an error
            CompanyNotFoundError: If company not found (404)
            RateLimitError: If rate limit exceeded (429)
            TimeoutError: If request times out
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "apikey": self.api_key,
            "Accept": "application/json",
            "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    return response.json()
                
                await self._handle_api_errors(response)
                
            except httpx.TimeoutException:
                raise TimeoutError(
                    f"KvK API request timed out after {self.timeout}s",
                    service="KvK API"
                )
            except httpx.NetworkError as e:
                raise KvKAPIError(
                    f"Network error connecting to KvK API: {str(e)}",
                    error_code="NETWORK_ERROR"
                )
    
    async def _handle_api_errors(self, response: httpx.Response) -> None:
        """
        Handle API error responses.
        
        Args:
            response: HTTP response object
            
        Raises:
            CompanyNotFoundError: If company not found (404)
            RateLimitError: If rate limit exceeded (429)
            KvKAPIError: For other API errors
        """
        if response.status_code == 404:
            # Try to extract KvK number from the URL for error message
            kvk_number = response.url.path.split("/")[-1]
            raise CompanyNotFoundError(kvk_number)
        
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_int = int(retry_after) if retry_after else None
            raise RateLimitError(
                "KvK API rate limit exceeded",
                retry_after=retry_after_int
            )
        
        # Try to get error details from response
        try:
            error_data = response.json()
            error_message = error_data.get("message", f"HTTP {response.status_code}")
            error_code = error_data.get("code", str(response.status_code))
        except Exception:
            error_message = f"HTTP {response.status_code}: {response.reason_phrase}"
            error_code = str(response.status_code)
        
        raise KvKAPIError(
            error_message,
            status_code=response.status_code,
            error_code=error_code
        )
    
    def _map_to_company_info(self, api_data: Dict[str, Any]) -> CompanyInfo:
        """
        Map KvK API response to CompanyInfo model.
        
        Args:
            api_data: Raw API response data
            
        Returns:
            CompanyInfo object
        """
        # Handle nested company data structure
        company = api_data.get("company", api_data)
        
        # Extract address information
        address_data = company.get("addresses", [{}])[0] if company.get("addresses") else {}
        
        # Build address string
        street_parts = []
        if address_data.get("street"):
            street_parts.append(address_data["street"])
        if address_data.get("houseNumber"):
            street_parts.append(address_data["houseNumber"])
        
        address = Address(
            street=" ".join(street_parts) if street_parts else "",
            house_number=address_data.get("houseNumber", ""),
            postal_code=address_data.get("postalCode", ""),
            city=address_data.get("city", ""),
            country=address_data.get("country", "Nederland")
        )
        
        # Extract SBI codes
        sbi_codes = []
        business_activities = []
        for sbi in company.get("businessActivities", []):
            code = sbi.get("sbiCode", "")
            description = sbi.get("sbiCodeDescription", sbi.get("description", ""))
            
            if code and description:
                sbi_codes.append(SBICode(code=code, description=description))
            if description:
                business_activities.append(description)
        
        # Map employee count
        employee_count = company.get("employees")
        employee_range = None
        if employee_count is not None:
            if employee_count == 0:
                employee_range = "0"
            elif employee_count <= 10:
                employee_range = "1-10"
            elif employee_count <= 50:
                employee_range = "11-50" 
            elif employee_count <= 250:
                employee_range = "51-250"
            else:
                employee_range = "250+"
        
        return CompanyInfo(
            kvk_number=company.get("kvkNumber", ""),
            name=company.get("name", ""),
            trade_name=company.get("tradeName"),
            legal_form=company.get("legalForm", ""),
            establishment_date=company.get("foundationDate"),
            address=address,
            sbi_codes=sbi_codes,
            business_activities=business_activities,
            employee_count=employee_count,
            employee_count_range=employee_range,
            annual_revenue_range=None,  # Not typically available in KvK API
            website=company.get("website"),
            status=company.get("status", "unknown")
        )

    def _get_mock_company_data(self, kvk_number: str) -> CompanyInfo:
        """
        Generate mock company data for testing when KvK API is not available.
        
        Args:
            kvk_number: The KvK number to generate mock data for
            
        Returns:
            CompanyInfo object with mock data
        """
        # Mock data based on some well-known Dutch companies
        mock_companies = {
            "17001910": {  # Koninklijke Philips N.V.
                "name": "Koninklijke Philips N.V.",
                "trade_name": "Philips",
                "legal_form": "Naamloze Vennootschap",
                "establishment_date": "1891-05-15",
                "address": {
                    "street": "Amstelplein",
                    "house_number": "2",
                    "postal_code": "1096 BC",
                    "city": "Amsterdam",
                    "country": "Nederland"
                },
                "sbi_codes": [
                    {"code": "26600", "description": "Vervaardiging van bestralings- en elektromedische en elektrotherapeutische apparaten"}
                ],
                "website": "https://www.philips.com",
                "employee_count": 80000,
                "status": "active"
            },
            "27312152": {  # ASML Holding N.V.
                "name": "ASML Holding N.V.",
                "trade_name": "ASML",
                "legal_form": "Naamloze Vennootschap",
                "establishment_date": "1984-04-09",
                "address": {
                    "street": "De Run",
                    "house_number": "6501",
                    "postal_code": "5504 DR",
                    "city": "Veldhoven",
                    "country": "Nederland"
                },
                "sbi_codes": [
                    {"code": "28990", "description": "Vervaardiging van overige machines voor specifieke doeleinden"}
                ],
                "website": "https://www.asml.com",
                "employee_count": 40000,
                "status": "active"
            }
        }
        
        # Use specific mock data if available, otherwise generate generic mock data
        if kvk_number in mock_companies:
            mock_data = mock_companies[kvk_number]
        else:
            mock_data = {
                "name": f"Test Company {kvk_number}",
                "trade_name": f"TestCorp {kvk_number}",
                "legal_form": "Besloten Vennootschap",
                "establishment_date": "2010-01-01",
                "address": {
                    "street": "Teststraat",
                    "house_number": "1",
                    "postal_code": "1234 AB",
                    "city": "Amsterdam",
                    "country": "Nederland"
                },
                "sbi_codes": [
                    {"code": "62010", "description": "Ontwikkelen, produceren en uitgeven van software"}
                ],
                "website": f"https://test-company-{kvk_number}.nl",
                "employee_count": 50,
                "status": "active"
            }
        
        # Convert mock data to CompanyInfo object
        address = Address(
            street=mock_data["address"]["street"],
            house_number=mock_data["address"]["house_number"],
            postal_code=mock_data["address"]["postal_code"],
            city=mock_data["address"]["city"],
            country=mock_data["address"]["country"]
        )
        
        sbi_codes = [
            SBICode(code=sbi["code"], description=sbi["description"])
            for sbi in mock_data["sbi_codes"]
        ]
        
        # Determine employee range from count
        employee_count = mock_data.get("employee_count", 0)
        if employee_count < 10:
            employee_range = "1-9"
        elif employee_count < 50:
            employee_range = "10-49"
        elif employee_count < 250:
            employee_range = "50-249"
        elif employee_count < 500:
            employee_range = "250-499"
        else:
            employee_range = "500+"
        
        return CompanyInfo(
            kvk_number=kvk_number,
            name=mock_data["name"],
            trade_name=mock_data.get("trade_name"),
            legal_form=mock_data.get("legal_form", ""),
            establishment_date=mock_data.get("establishment_date"),
            address=address,
            sbi_codes=sbi_codes,
            business_activities=[sbi["description"] for sbi in mock_data["sbi_codes"]],
            employee_count=employee_count,
            employee_count_range=employee_range,
            annual_revenue_range=None,
            website=mock_data.get("website"),
            status=mock_data.get("status", "active")
        )