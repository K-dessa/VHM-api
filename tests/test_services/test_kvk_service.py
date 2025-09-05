"""
Tests for KvK Service.
"""

import pytest
from unittest.mock import AsyncMock, Mock
import httpx
from datetime import datetime

from app.services.kvk_service import KvKService
from app.models.response_models import CompanyInfo, Address, SBICode
from app.core.exceptions import (
    KvKAPIError, CompanyNotFoundError, TimeoutError, RateLimitError
)


@pytest.fixture
def kvk_service():
    """Create KvK service instance for testing."""
    # Mock the settings to avoid needing actual API key
    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.services.kvk_service.settings.KVK_API_KEY", "test_key")
        m.setattr("app.services.kvk_service.settings.KVK_BASE_URL", "https://api.kvk.nl/api/v1/")
        m.setattr("app.services.kvk_service.settings.KVK_TIMEOUT", 10)
        return KvKService()


@pytest.fixture
def sample_kvk_response():
    """Sample KvK API response data."""
    return {
        "company": {
            "kvkNumber": "69599084",
            "name": "Test Company B.V.",
            "tradeName": "Test Company",
            "legalForm": "Besloten vennootschap",
            "foundationDate": "2020-01-15T00:00:00Z",
            "status": "active",
            "employees": 25,
            "website": "https://testcompany.nl",
            "addresses": [
                {
                    "street": "Teststraat",
                    "houseNumber": "123",
                    "postalCode": "1234 AB",
                    "city": "Amsterdam",
                    "country": "Nederland"
                }
            ],
            "businessActivities": [
                {
                    "sbiCode": "6201",
                    "sbiCodeDescription": "Ontwikkelen, produceren en uitgeven van software"
                },
                {
                    "sbiCode": "6202",
                    "sbiCodeDescription": "Advisering en ondersteuning op het gebied van informatietechnologie"
                }
            ]
        }
    }


@pytest.fixture
def expected_company_info():
    """Expected CompanyInfo object from sample data."""
    address = Address(
        street="Teststraat 123",
        house_number="123",
        postal_code="1234 AB",
        city="Amsterdam",
        country="Nederland"
    )
    
    sbi_codes = [
        SBICode(code="6201", description="Ontwikkelen, produceren en uitgeven van software"),
        SBICode(code="6202", description="Advisering en ondersteuning op het gebied van informatietechnologie")
    ]
    
    return CompanyInfo(
        kvk_number="69599084",
        name="Test Company B.V.",
        trade_name="Test Company",
        legal_form="Besloten vennootschap",
        establishment_date=datetime.fromisoformat("2020-01-15T00:00:00+00:00"),
        address=address,
        sbi_codes=sbi_codes,
        business_activities=[
            "Ontwikkelen, produceren en uitgeven van software",
            "Advisering en ondersteuning op het gebied van informatietechnologie"
        ],
        employee_count=25,
        employee_count_range="11-50",
        annual_revenue_range=None,
        website="https://testcompany.nl",
        status="active"
    )


class TestKvKNumberValidation:
    """Test KvK number validation."""

    def test_validate_kvk_number_valid(self, kvk_service):
        """Test validation of valid KvK numbers."""
        valid_numbers = [
            "69599084",
            "27312140",
            "73576017"
        ]
        
        for kvk_number in valid_numbers:
            assert kvk_service.validate_kvk_number(kvk_number)

    def test_validate_kvk_number_invalid_format(self, kvk_service):
        """Test validation of invalid KvK number formats."""
        invalid_numbers = [
            "",              # Empty
            "1234567",       # Too short
            "123456789",     # Too long
            "abcd1234",      # Contains letters
            "12-34-56-78",   # Valid format but invalid checksum
            "12345678",      # Invalid checksum
        ]
        
        for kvk_number in invalid_numbers:
            assert not kvk_service.validate_kvk_number(kvk_number)

    def test_validate_kvk_number_with_formatting(self, kvk_service):
        """Test validation with various formatting."""
        # Valid number with different formatting
        assert kvk_service.validate_kvk_number("6959-9084")
        assert kvk_service.validate_kvk_number("6959 9084")
        assert kvk_service.validate_kvk_number(" 69599084 ")


class TestKvKServiceAPIRequests:
    """Test KvK Service API requests."""

    @pytest.mark.asyncio
    async def test_get_company_info_success(self, kvk_service, sample_kvk_response, expected_company_info):
        """Test successful company info retrieval."""
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_kvk_response
        
        # Mock httpx client
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            result = await kvk_service.get_company_info("69599084")
            
            # Verify the result matches expectations
            assert result.kvk_number == expected_company_info.kvk_number
            assert result.name == expected_company_info.name
            assert result.trade_name == expected_company_info.trade_name
            assert result.legal_form == expected_company_info.legal_form
            assert result.address.street == expected_company_info.address.street
            assert len(result.sbi_codes) == len(expected_company_info.sbi_codes)
            assert result.employee_count == expected_company_info.employee_count
            assert result.status == expected_company_info.status

    @pytest.mark.asyncio
    async def test_get_company_info_invalid_kvk_format(self, kvk_service):
        """Test error handling for invalid KvK number format."""
        
        with pytest.raises(KvKAPIError) as exc_info:
            await kvk_service.get_company_info("invalid")
        
        assert "Invalid KvK number format" in str(exc_info.value)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_company_info_not_found(self, kvk_service):
        """Test handling of company not found (404)."""
        
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.url.path = "/companies/12345678"
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            with pytest.raises(CompanyNotFoundError) as exc_info:
                await kvk_service.get_company_info("12345678")
            
            assert exc_info.value.kvk_number == "12345678"

    @pytest.mark.asyncio
    async def test_get_company_info_rate_limit(self, kvk_service):
        """Test handling of rate limit (429)."""
        
        # Mock 429 response with retry-after header
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            with pytest.raises(RateLimitError) as exc_info:
                await kvk_service.get_company_info("69599084")
            
            assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_get_company_info_timeout(self, kvk_service):
        """Test handling of request timeout."""
        
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            with pytest.raises(TimeoutError) as exc_info:
                await kvk_service.get_company_info("69599084")
            
            assert "timed out" in str(exc_info.value)
            assert exc_info.value.service == "KvK API"

    @pytest.mark.asyncio
    async def test_get_company_info_network_error(self, kvk_service):
        """Test handling of network errors."""
        
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.NetworkError("Connection failed")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            with pytest.raises(KvKAPIError) as exc_info:
                await kvk_service.get_company_info("69599084")
            
            assert "Network error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_company_info_api_error(self, kvk_service):
        """Test handling of other API errors."""
        
        # Mock 500 response with error details
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "message": "Internal server error",
            "code": "INTERNAL_ERROR"
        }
        mock_response.reason_phrase = "Internal Server Error"
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            with pytest.raises(KvKAPIError) as exc_info:
                await kvk_service.get_company_info("69599084")
            
            assert exc_info.value.status_code == 500
            assert "Internal server error" in str(exc_info.value)


class TestKvKServiceRetryLogic:
    """Test retry logic in KvK Service."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, kvk_service, sample_kvk_response):
        """Test retry logic on timeout errors."""
        
        call_count = 0
        
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 calls
                raise httpx.TimeoutException("Request timed out")
            # Succeed on 3rd call
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_kvk_response
            return mock_response
        
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
            
            # Should succeed after retries
            result = await kvk_service.get_company_info("69599084")
            assert result.kvk_number == "69599084"
            assert call_count == 3  # Verify it retried


class TestKvKServiceDataMapping:
    """Test data mapping functionality."""

    def test_map_to_company_info_minimal_data(self, kvk_service):
        """Test mapping with minimal KvK data."""
        minimal_data = {
            "company": {
                "kvkNumber": "12345678",
                "name": "Minimal Company",
                "legalForm": "Eenmanszaak",
                "status": "active",
                "addresses": [
                    {
                        "street": "Simple Street",
                        "houseNumber": "1",
                        "postalCode": "1000 AA",
                        "city": "Test City"
                    }
                ],
                "businessActivities": []
            }
        }
        
        result = kvk_service._map_to_company_info(minimal_data)
        
        assert result.kvk_number == "12345678"
        assert result.name == "Minimal Company"
        assert result.legal_form == "Eenmanszaak"
        assert result.status == "active"
        assert result.address.street == "Simple Street 1"
        assert result.address.city == "Test City"
        assert len(result.sbi_codes) == 0
        assert result.employee_count is None

    def test_map_to_company_info_employee_ranges(self, kvk_service):
        """Test employee count range mapping."""
        test_cases = [
            (0, "0"),
            (5, "1-10"),
            (25, "11-50"),
            (150, "51-250"),
            (500, "250+")
        ]
        
        for employee_count, expected_range in test_cases:
            data = {
                "company": {
                    "kvkNumber": "12345678",
                    "name": "Test Company",
                    "legalForm": "BV",
                    "status": "active",
                    "employees": employee_count,
                    "addresses": [{"street": "Test", "city": "Test", "postalCode": "1000 AA"}],
                    "businessActivities": []
                }
            }
            
            result = kvk_service._map_to_company_info(data)
            assert result.employee_count_range == expected_range
            assert result.employee_count == employee_count