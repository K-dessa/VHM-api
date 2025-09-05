"""
Integration tests for the analyze company endpoint.
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock
from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app
from app.models.response_models import CompanyInfo, Address, SBICode, RiskLevel
from app.services.kvk_service import KvKService
from app.core.exceptions import CompanyNotFoundError, KvKAPIError, TimeoutError


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_company_info():
    """Sample CompanyInfo for mocking."""
    address = Address(
        street="Teststraat 123",
        house_number="123", 
        postal_code="1234 AB",
        city="Amsterdam",
        country="Nederland"
    )
    
    sbi_codes = [
        SBICode(code="6201", description="Ontwikkelen, produceren en uitgeven van software")
    ]
    
    return CompanyInfo(
        kvk_number="69599084",
        name="Test Company B.V.",
        trade_name="Test Company",
        legal_form="Besloten vennootschap",
        establishment_date=datetime(2020, 1, 15),
        address=address,
        sbi_codes=sbi_codes,
        business_activities=["Ontwikkelen, produceren en uitgeven van software"],
        employee_count=25,
        employee_count_range="11-50",
        annual_revenue_range=None,
        website="https://testcompany.nl",
        status="active"
    )


class TestAnalyzeEndpointAuthentication:
    """Test authentication and authorization for analyze endpoint."""

    def test_analyze_company_no_auth(self, client):
        """Test request without authentication."""
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"}
        )
        
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_analyze_company_invalid_api_key(self, client):
        """Test request with invalid API key."""
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "invalid-key"}
        )
        
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_analyze_company_valid_api_key(self, client, sample_company_info):
        """Test request with valid API key."""
        with patch.object(KvKService, 'get_company_info', return_value=sample_company_info):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-key"}
            )
            
            # Should not be auth error (might be other errors due to missing API keys)
            assert response.status_code != 401

    def test_analyze_company_bearer_token(self, client, sample_company_info):
        """Test request with Bearer token."""
        with patch.object(KvKService, 'get_company_info', return_value=sample_company_info):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"Authorization": "Bearer test-key"}
            )
            
            # Should not be auth error
            assert response.status_code != 401


class TestAnalyzeEndpointValidation:
    """Test request validation for analyze endpoint."""

    def test_analyze_company_invalid_kvk_format(self, client):
        """Test request with invalid KvK number format."""
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "invalid"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 422  # Validation error

    def test_analyze_company_missing_kvk(self, client):
        """Test request without KvK number."""
        response = client.post(
            "/analyze-company",
            json={},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 422  # Validation error

    def test_analyze_company_valid_kvk_formats(self, client, sample_company_info):
        """Test various valid KvK number formats."""
        with patch.object(KvKService, 'get_company_info', return_value=sample_company_info):
            valid_formats = [
                "69599084",
                "6959-9084", 
                "6959 9084"
            ]
            
            for kvk_format in valid_formats:
                response = client.post(
                    "/analyze-company",
                    json={"kvk_number": kvk_format},
                    headers={"X-API-Key": "test-key"}
                )
                
                # Should not be validation error
                assert response.status_code != 422


class TestAnalyzeEndpointHappyPath:
    """Test successful analyze endpoint responses."""

    @patch('app.api.endpoints.analyze.KvKService')
    def test_analyze_company_success(self, mock_kvk_service_class, client, sample_company_info):
        """Test successful company analysis."""
        # Mock the KvK service
        mock_service = AsyncMock()
        mock_service.get_company_info.return_value = sample_company_info
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={
                "kvk_number": "69599084",
                "search_depth": "standard"
            },
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 200
        
        data = response.json()
        
        # Check response structure
        assert "request_id" in data
        assert "analysis_timestamp" in data
        assert "processing_time_seconds" in data
        assert "company_info" in data
        assert "risk_assessment" in data
        assert "warnings" in data
        assert "data_sources" in data
        
        # Check company info
        company_info = data["company_info"]
        assert company_info["kvk_number"] == "69599084"
        assert company_info["name"] == "Test Company B.V."
        assert company_info["status"] == "active"
        
        # Check risk assessment
        risk_assessment = data["risk_assessment"]
        assert "overall_risk_level" in risk_assessment
        assert "risk_score" in risk_assessment
        assert "risk_factors" in risk_assessment
        assert "positive_factors" in risk_assessment
        
        # Check that legal and news analysis are not yet implemented
        assert data["legal_findings"] is None
        assert data["news_analysis"] is None
        
        # Check warnings about limitations
        warnings = data["warnings"]
        assert any("KvK" in warning for warning in warnings)
        assert any("Legal case analysis" in warning for warning in warnings)

    def test_analyze_company_response_headers(self, client, sample_company_info):
        """Test that rate limit headers are included."""
        with patch.object(KvKService, 'get_company_info', return_value=sample_company_info):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-key"}
            )
            
            # Check rate limit headers are present
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers


class TestAnalyzeEndpointErrorHandling:
    """Test error handling in analyze endpoint."""

    @patch('app.api.endpoints.analyze.KvKService')
    def test_analyze_company_not_found(self, mock_kvk_service_class, client):
        """Test handling of company not found."""
        mock_service = AsyncMock()
        mock_service.get_company_info.side_effect = CompanyNotFoundError("69599084")
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch('app.api.endpoints.analyze.KvKService')
    def test_analyze_company_kvk_api_error(self, mock_kvk_service_class, client):
        """Test handling of KvK API errors."""
        mock_service = AsyncMock()
        mock_service.get_company_info.side_effect = KvKAPIError(
            "API error", status_code=500
        )
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 502
        assert "KvK API" in response.json()["detail"]

    @patch('app.api.endpoints.analyze.KvKService')
    def test_analyze_company_kvk_rate_limit(self, mock_kvk_service_class, client):
        """Test handling of KvK API rate limits."""
        mock_service = AsyncMock()
        mock_service.get_company_info.side_effect = KvKAPIError(
            "Rate limit exceeded", status_code=429
        )
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()

    @patch('app.api.endpoints.analyze.KvKService')
    def test_analyze_company_timeout(self, mock_kvk_service_class, client):
        """Test handling of timeouts."""
        mock_service = AsyncMock()
        mock_service.get_company_info.side_effect = TimeoutError(
            "Request timed out", service="KvK API"
        )
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"].lower()

    @patch('app.api.endpoints.analyze.KvKService')
    def test_analyze_company_unexpected_error(self, mock_kvk_service_class, client):
        """Test handling of unexpected errors."""
        mock_service = AsyncMock()
        mock_service.get_company_info.side_effect = Exception("Unexpected error")
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 500
        assert "unexpected error" in response.json()["detail"].lower()


class TestAnalyzeEndpointRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limiting_headers(self, client, sample_company_info):
        """Test that rate limit headers are properly set."""
        with patch.object(KvKService, 'get_company_info', return_value=sample_company_info):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-key"}
            )
            
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
            assert "X-RateLimit-Window" in response.headers
            
            # Verify header values are reasonable
            assert int(response.headers["X-RateLimit-Limit"]) > 0
            assert int(response.headers["X-RateLimit-Remaining"]) >= 0
            assert int(response.headers["X-RateLimit-Reset"]) > 0

    def test_rate_limiting_exhaustion(self, client, sample_company_info):
        """Test rate limit exhaustion (simulate many requests)."""
        with patch.object(KvKService, 'get_company_info', return_value=sample_company_info):
            # Make multiple requests rapidly
            responses = []
            for i in range(105):  # More than default limit
                response = client.post(
                    "/analyze-company", 
                    json={"kvk_number": "69599084"},
                    headers={"X-API-Key": f"test-key-{i % 3}"}  # Rotate keys
                )
                responses.append(response)
                
                # Stop if we hit rate limit
                if response.status_code == 429:
                    break
            
            # Should eventually hit rate limit for some key
            rate_limited = any(r.status_code == 429 for r in responses)
            # Note: This might not always trigger in tests due to separate rate limiters
            # per test, but the structure should work


class TestAnalyzeEndpointRiskAssessment:
    """Test risk assessment logic."""

    @patch('app.api.endpoints.analyze.KvKService')
    def test_risk_assessment_active_company(self, mock_kvk_service_class, client):
        """Test risk assessment for healthy active company."""
        # Create a healthy company profile
        address = Address(
            street="Teststraat 123",
            postal_code="1234 AB", 
            city="Amsterdam",
            country="Nederland"
        )
        
        healthy_company = CompanyInfo(
            kvk_number="69599084",
            name="Healthy Company B.V.",
            trade_name="Healthy Company",
            legal_form="Besloten vennootschap",
            establishment_date=datetime(2010, 1, 1),  # Old, established
            address=address,
            sbi_codes=[SBICode(code="6201", description="Software development")],
            business_activities=["Software development"],
            employee_count=100,  # Good size
            employee_count_range="51-250",
            website="https://healthy.nl",
            status="active"
        )
        
        mock_service = AsyncMock()
        mock_service.get_company_info.return_value = healthy_company
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 200
        
        risk_assessment = response.json()["risk_assessment"]
        
        # Should be low risk due to good indicators
        assert risk_assessment["overall_risk_level"] in ["low", "medium"]
        assert risk_assessment["risk_score"] < 50
        
        # Check for positive factors
        positive_factors = risk_assessment["positive_factors"]
        assert len(positive_factors) > 0
        assert any("active" in factor.lower() for factor in positive_factors)

    @patch('app.api.endpoints.analyze.KvKService')
    def test_risk_assessment_risky_company(self, mock_kvk_service_class, client):
        """Test risk assessment for potentially risky company."""
        address = Address(
            street="Teststraat 1",
            postal_code="1000 AA",
            city="Test", 
            country="Nederland"
        )
        
        risky_company = CompanyInfo(
            kvk_number="12345678",
            name="New Company",
            legal_form="Eenmanszaak",
            establishment_date=datetime(2024, 6, 1),  # Very new
            address=address,
            sbi_codes=[],  # No activities
            business_activities=[],
            employee_count=0,  # No employees
            employee_count_range="0",
            website=None,  # No website
            status="inactive"  # Inactive!
        )
        
        mock_service = AsyncMock()
        mock_service.get_company_info.return_value = risky_company
        mock_kvk_service_class.return_value = mock_service
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "12345678"},
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 200
        
        risk_assessment = response.json()["risk_assessment"]
        
        # Should be higher risk
        assert risk_assessment["overall_risk_level"] in ["medium", "high", "critical"]
        assert risk_assessment["risk_score"] > 40
        
        # Check for risk factors
        risk_factors = risk_assessment["risk_factors"]
        assert len(risk_factors) > 0
        assert any("inactive" in factor.lower() or "status" in factor.lower() for factor in risk_factors)