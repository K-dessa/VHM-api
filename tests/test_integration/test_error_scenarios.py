"""
Integration tests for error scenarios and failure handling.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.exceptions import (
    KvKAPIError, CompanyNotFoundError, TimeoutError, 
    RateLimitError, ValidationError
)


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


class TestServiceFailureCombinations:
    """Test different combinations of service failures."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    def test_kvk_service_failure_404(self, mock_kvk_info, client):
        """Test handling when company is not found in KvK."""
        
        mock_kvk_info.side_effect = CompanyNotFoundError("69599084")
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "Company with KvK number 69599084 not found" in data["detail"]
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    def test_kvk_api_error_502(self, mock_kvk_info, client):
        """Test handling when KvK API returns error."""
        
        mock_kvk_info.side_effect = KvKAPIError("KvK API unavailable", 503)
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 502
        data = response.json()
        assert "Error communicating with KvK API" in data["detail"]
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    def test_kvk_rate_limit_error(self, mock_kvk_info, client):
        """Test handling when KvK API rate limit is exceeded."""
        
        mock_kvk_info.side_effect = KvKAPIError("Rate limit exceeded", 429)
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 429
        data = response.json()
        assert "KvK API rate limit exceeded" in data["detail"]
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_legal_service_failure_graceful_degradation(
        self,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client
    ):
        """Test graceful degradation when legal service fails."""
        
        from app.models.responses import CompanyInfo
        from datetime import datetime, timedelta
        
        # KvK succeeds
        mock_company_info = CompanyInfo(
            kvk_number="69599084",
            name="Test Company B.V.",
            trade_name="TestCorp",
            status="Actief",
            establishment_date=datetime.now() - timedelta(days=365),
            address="Test Address",
            postal_code="1234AB",
            city="Amsterdam",
            country="Nederland",
            sbi_codes=["6201"],
            employee_count=10,
            legal_form="BV"
        )
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        
        # Legal service fails
        mock_legal_search.side_effect = Exception("Legal service timeout")
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                response = client.post(
                    "/analyze-company",
                    json={"kvk_number": "69599084"},
                    headers={"X-API-Key": "test-api-key"}
                )
        
        # Should succeed with partial data
        assert response.status_code == 200
        data = response.json()
        
        # Should have company info but no legal data
        assert data["company_info"] is not None
        assert data["legal_findings"] is None
        assert data["news_analysis"] is None
        
        # Should have appropriate warning
        warnings = " ".join(data["warnings"]).lower()
        assert "legal case analysis was not available" in warnings
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_news_service_failure_graceful_degradation(
        self,
        mock_news_search,
        mock_legal_init,
        mock_kvk_info,
        client
    ):
        """Test graceful degradation when news service fails."""
        
        from app.models.responses import CompanyInfo
        from datetime import datetime, timedelta
        
        mock_company_info = CompanyInfo(
            kvk_number="69599084",
            name="Test Company B.V.",
            trade_name="TestCorp", 
            status="Actief",
            establishment_date=datetime.now() - timedelta(days=365),
            address="Test Address",
            postal_code="1234AB",
            city="Amsterdam",
            country="Nederland",
            sbi_codes=["6201"],
            employee_count=10,
            legal_form="BV"
        )
        
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        mock_news_search.side_effect = Exception("OpenAI API timeout")
        
        with patch('app.services.legal_service.LegalService.robots_allowed', False):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        # Should succeed with partial data
        assert response.status_code == 200
        data = response.json()
        
        # Should have company info but no news data
        assert data["company_info"] is not None
        assert data["legal_findings"] is None
        assert data["news_analysis"] is None


class TestTimeoutScenarios:
    """Test timeout handling in various scenarios."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    def test_kvk_service_timeout(self, mock_kvk_info, client):
        """Test timeout when KvK service takes too long."""
        
        async def slow_kvk_response():
            await asyncio.sleep(70)  # Longer than 60s timeout
            return None
        
        mock_kvk_info.side_effect = slow_kvk_response
        
        response = client.post(
            "/analyze-company",
            json={
                "kvk_number": "69599084",
                "search_depth": "deep"  # 60s timeout
            },
            headers={"X-API-Key": "test-api-key"}
        )
        
        # Should timeout gracefully
        assert response.status_code == 504
        data = response.json()
        assert "timed out" in data["detail"].lower()
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_partial_timeout_recovery(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client
    ):
        """Test recovery when some services timeout but others succeed."""
        
        from app.models.responses import CompanyInfo
        from datetime import datetime, timedelta
        
        mock_company_info = CompanyInfo(
            kvk_number="69599084",
            name="Test Company B.V.",
            trade_name="TestCorp",
            status="Actief", 
            establishment_date=datetime.now() - timedelta(days=365),
            address="Test Address",
            postal_code="1234AB",
            city="Amsterdam",
            country="Nederland",
            sbi_codes=["6201"],
            employee_count=10,
            legal_form="BV"
        )
        
        # KvK succeeds quickly
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        
        # Legal service times out
        async def slow_legal_response():
            await asyncio.sleep(35)  # Longer than standard timeout
            return []
        
        # News service times out
        async def slow_news_response():
            await asyncio.sleep(35)
            return None
        
        mock_legal_search.side_effect = slow_legal_response
        mock_news_search.side_effect = slow_news_response
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={
                    "kvk_number": "69599084",
                    "search_depth": "standard"  # 30s timeout
                },
                headers={"X-API-Key": "test-api-key"}
            )
        
        # Should succeed with partial data (company info only)
        assert response.status_code == 200
        data = response.json()
        
        assert data["company_info"] is not None
        # Other services should have timed out
        assert data["legal_findings"] is None
        assert data["news_analysis"] is None
        
        # Should have warning about timeout
        warnings = " ".join(data["warnings"]).lower()
        assert "timed out" in warnings or "partial" in warnings


class TestRateLimitingBehavior:
    """Test rate limiting behavior under load."""
    
    def test_api_key_rate_limiting(self, client):
        """Test that rate limiting works correctly."""
        
        # Mock the rate limiter to simulate rate limit exceeded
        with patch('app.utils.rate_limiter.RateLimiter.check_rate_limit') as mock_check:
            mock_check.side_effect = RateLimitError("Rate limit exceeded", 3600)
            
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        
        data = response.json()
        assert "rate limit" in data["message"].lower()
    
    def test_concurrent_requests_same_api_key(self, client):
        """Test behavior with concurrent requests from same API key."""
        
        # This would be better tested with actual concurrent requests
        # but for integration testing, we'll simulate the rate limiter state
        
        with patch('app.services.kvk_service.KvKService.get_company_info') as mock_kvk:
            from app.models.responses import CompanyInfo
            from datetime import datetime, timedelta
            
            mock_company_info = CompanyInfo(
                kvk_number="69599084",
                name="Test Company B.V.",
                trade_name="TestCorp",
                status="Actief",
                establishment_date=datetime.now() - timedelta(days=365),
                address="Test Address",
                postal_code="1234AB",
                city="Amsterdam",
                country="Nederland",
                sbi_codes=["6201"],
                employee_count=10,
                legal_form="BV"
            )
            
            mock_kvk.return_value = mock_company_info
            
            # Make multiple requests quickly
            responses = []
            for i in range(3):
                response = client.post(
                    "/analyze-company",
                    json={"kvk_number": "69599084"},
                    headers={"X-API-Key": "test-api-key-concurrent"}
                )
                responses.append(response)
            
            # All should succeed (assuming rate limit not exceeded)
            for response in responses:
                assert response.status_code in [200, 429]  # Either success or rate limited


class TestAuthenticationFailures:
    """Test authentication and authorization failures."""
    
    def test_missing_api_key(self, client):
        """Test request without API key."""
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"}
        )
        
        assert response.status_code == 403
        data = response.json()
        assert "API key required" in data["detail"] or "Forbidden" in data["detail"]
    
    def test_invalid_api_key_format(self, client):
        """Test request with invalid API key format."""
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": "invalid-key"}
        )
        
        # Depending on implementation, this might be 401 or 403
        assert response.status_code in [401, 403]
    
    def test_empty_api_key(self, client):
        """Test request with empty API key."""
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": "69599084"},
            headers={"X-API-Key": ""}
        )
        
        assert response.status_code in [401, 403]


class TestInputValidationFailures:
    """Test various input validation failures."""
    
    def test_invalid_kvk_number_format(self, client):
        """Test invalid KvK number formats."""
        
        invalid_kvk_numbers = [
            "invalid",
            "123",
            "1234567890123",  # Too long
            "",
            None
        ]
        
        for kvk_number in invalid_kvk_numbers:
            response = client.post(
                "/analyze-company",
                json={"kvk_number": kvk_number},
                headers={"X-API-Key": "test-api-key"}
            )
            
            assert response.status_code == 400, f"Failed for KvK number: {kvk_number}"
            data = response.json()
            assert "validation" in data["error"].lower() or "invalid" in data["message"].lower()
    
    def test_invalid_search_depth(self, client):
        """Test invalid search depth values."""
        
        response = client.post(
            "/analyze-company",
            json={
                "kvk_number": "69599084",
                "search_depth": "invalid_depth"
            },
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "validation" in data["error"].lower()
    
    def test_invalid_date_range(self, client):
        """Test invalid date range values."""
        
        response = client.post(
            "/analyze-company", 
            json={
                "kvk_number": "69599084",
                "date_range": "invalid_range"
            },
            headers={"X-API-Key": "test-api-key"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "validation" in data["error"].lower()
    
    def test_oversized_request_payload(self, client):
        """Test request payload that exceeds size limit."""
        
        # Create a very large request (this might not trigger the size limit check
        # in test environment, but demonstrates the test approach)
        large_kvk_number = "1" * 1000000  # 1MB of data
        
        response = client.post(
            "/analyze-company",
            json={"kvk_number": large_kvk_number},
            headers={
                "X-API-Key": "test-api-key",
                "Content-Length": "1048577"  # Just over 1MB
            }
        )
        
        # Should be rejected for payload size
        assert response.status_code in [400, 413]
    
    def test_malformed_json_request(self, client):
        """Test request with malformed JSON."""
        
        response = client.post(
            "/analyze-company",
            data="{'invalid': json}",  # Malformed JSON
            headers={
                "X-API-Key": "test-api-key",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 400


class TestErrorResponseConsistency:
    """Test that error responses follow consistent format."""
    
    def test_error_response_format_404(self, client):
        """Test 404 error response format."""
        
        with patch('app.services.kvk_service.KvKService.get_company_info') as mock_kvk:
            mock_kvk.side_effect = CompanyNotFoundError("69599084")
            
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 404
        data = response.json()
        
        # Check error response structure
        assert "detail" in data
        assert isinstance(data["detail"], str)
    
    def test_error_response_format_500(self, client):
        """Test 500 error response format."""
        
        with patch('app.services.kvk_service.KvKService.get_company_info') as mock_kvk:
            mock_kvk.side_effect = Exception("Unexpected error")
            
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 500
        data = response.json()
        
        # Check error response structure
        assert "detail" in data
        assert "internal server error" in data["detail"].lower()
    
    def test_all_error_responses_have_correlation_id(self, client):
        """Test that all error responses include correlation ID."""
        
        with patch('app.services.kvk_service.KvKService.get_company_info') as mock_kvk:
            mock_kvk.side_effect = CompanyNotFoundError("69599084")
            
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        # Check that correlation ID is in headers
        assert "X-Correlation-ID" in response.headers
        assert len(response.headers["X-Correlation-ID"]) > 0