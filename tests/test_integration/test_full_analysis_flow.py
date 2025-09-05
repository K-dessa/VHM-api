"""
End-to-end integration tests for the full analysis flow.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.models.responses import CompanyInfo, LegalCase, NewsAnalysis
from app.services.risk_service import RiskLevel


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def mock_company_info():
    """Mock company information."""
    return CompanyInfo(
        kvk_number="69599084",
        name="Test Company B.V.",
        trade_name="TestCorp",
        status="Actief",
        establishment_date=datetime.now() - timedelta(days=365 * 5),
        address="Teststraat 1, 1234 AB Amsterdam",
        postal_code="1234AB",
        city="Amsterdam",
        country="Nederland",
        phone="+31 20 1234567",
        website="https://www.testcompany.nl",
        email="info@testcompany.nl",
        sbi_codes=["6201", "6202"],
        employee_count=25,
        legal_form="Besloten Vennootschap"
    )


@pytest.fixture
def mock_legal_cases():
    """Mock legal cases."""
    return [
        LegalCase(
            case_id="TEST001",
            date=datetime.now() - timedelta(days=30),
            case_type="Civiel",
            summary="Contract dispute resolved in favor of defendant",
            outcome="Dismissed",
            court="Rechtbank Amsterdam",
            parties=["Test Company B.V.", "Plaintiff Corp"]
        ),
        LegalCase(
            case_id="TEST002", 
            date=datetime.now() - timedelta(days=180),
            case_type="Administratief",
            summary="Minor regulatory compliance issue",
            outcome="Warning issued",
            court="CBb",
            parties=["Test Company B.V.", "Regulatory Authority"]
        )
    ]


@pytest.fixture
def mock_news_analysis():
    """Mock news analysis."""
    return NewsAnalysis(
        total_articles_found=8,
        total_relevance=0.85,
        overall_sentiment=0.2,
        sentiment_summary={
            "positive": 60,
            "neutral": 30,
            "negative": 10
        },
        key_topics=[
            "Business Growth",
            "New Partnership",
            "Innovation",
            "Market Expansion"
        ],
        risk_indicators=[],
        positive_news={
            "count": 5,
            "themes": ["growth", "partnership", "innovation"]
        },
        negative_news={
            "count": 1,
            "themes": ["minor complaint"]
        },
        articles=[
            {
                "title": "Test Company Announces New Partnership",
                "summary": "Leading company forms strategic alliance",
                "date": "2024-01-15",
                "sentiment": 0.7,
                "relevance": 0.9
            }
        ]
    )


class TestFullAnalysisFlowHappyPath:
    """Test complete analysis flow under normal conditions."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_complete_analysis_success(
        self, 
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_info,
        mock_legal_cases,
        mock_news_analysis
    ):
        """Test successful complete analysis with all services."""
        
        # Setup mocks
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        mock_legal_search.return_value = mock_legal_cases
        mock_news_search.return_value = mock_news_analysis
        
        # Mock legal service robots check
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={
                    "kvk_number": "69599084",
                    "search_depth": "standard",
                    "date_range": "1y",
                    "include_positive": True,
                    "include_negative": True,
                    "language": "nl"
                },
                headers={"X-API-Key": "test-api-key"}
            )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "request_id" in data
        assert "analysis_timestamp" in data
        assert "processing_time_seconds" in data
        assert "company_info" in data
        assert "legal_findings" in data
        assert "news_analysis" in data
        assert "risk_assessment" in data
        assert "warnings" in data
        assert "data_sources" in data
        
        # Check company info
        assert data["company_info"]["kvk_number"] == "69599084"
        assert data["company_info"]["name"] == "Test Company B.V."
        
        # Check legal findings
        assert data["legal_findings"]["total_cases"] == 2
        assert len(data["legal_findings"]["cases"]) == 2
        
        # Check news analysis
        assert data["news_analysis"]["total_articles_found"] == 8
        assert data["news_analysis"]["overall_sentiment"] == 0.2
        
        # Check risk assessment exists
        assert "overall_risk_level" in data["risk_assessment"]
        assert "risk_score" in data["risk_assessment"]
        assert "risk_factors" in data["risk_assessment"]
        assert "recommendations" in data["risk_assessment"]
        
        # Check data sources
        expected_sources = [
            "KvK (Dutch Chamber of Commerce)",
            "Rechtspraak.nl (Dutch Legal Database)",
            "AI-powered news analysis (OpenAI)"
        ]
        for source in expected_sources:
            assert source in data["data_sources"]
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_analysis_with_kvk_only(
        self,
        mock_legal_init,
        mock_kvk_info,
        client,
        mock_company_info
    ):
        """Test analysis when only KvK service is available."""
        
        # Setup mocks - KvK succeeds, others fail/unavailable
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        
        # Mock legal service as not allowed by robots.txt
        with patch('app.services.legal_service.LegalService.robots_allowed', False):
            # Mock NewsService initialization failure (no OpenAI key)
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("OpenAI API key not configured")):
                response = client.post(
                    "/analyze-company",
                    json={
                        "kvk_number": "69599084",
                        "search_depth": "standard"
                    },
                    headers={"X-API-Key": "test-api-key"}
                )
        
        # Assertions
        assert response.status_code == 200
        data = response.json()
        
        # Should have company info but no legal/news data
        assert data["company_info"]["kvk_number"] == "69599084"
        assert data["legal_findings"] is None
        assert data["news_analysis"] is None
        
        # Should still have risk assessment (basic)
        assert "risk_assessment" in data
        
        # Should have appropriate warnings
        warnings = data["warnings"]
        assert any("Legal case analysis was not available" in warning for warning in warnings)
        assert any("News sentiment analysis was not available" in warning for warning in warnings)
        
        # Data sources should only include KvK
        assert len(data["data_sources"]) == 1
        assert "KvK (Dutch Chamber of Commerce)" in data["data_sources"]


class TestAnalysisResponseValidation:
    """Test response format and data validation."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_response_format_validation(
        self,
        mock_legal_init,
        mock_kvk_info,
        client,
        mock_company_info
    ):
        """Test that response follows the expected schema."""
        
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        
        with patch('app.services.legal_service.LegalService.robots_allowed', False):
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                response = client.post(
                    "/analyze-company",
                    json={"kvk_number": "69599084"},
                    headers={"X-API-Key": "test-api-key"}
                )
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate required top-level fields
        required_fields = [
            "request_id", "analysis_timestamp", "processing_time_seconds",
            "company_info", "legal_findings", "news_analysis", 
            "risk_assessment", "warnings", "data_sources"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Validate data types
        assert isinstance(data["request_id"], str)
        assert isinstance(data["processing_time_seconds"], (int, float))
        assert isinstance(data["warnings"], list)
        assert isinstance(data["data_sources"], list)
        
        # Validate risk assessment structure
        risk_assessment = data["risk_assessment"]
        assert "overall_risk_level" in risk_assessment
        assert "risk_score" in risk_assessment
        assert "risk_factors" in risk_assessment
        assert "recommendations" in risk_assessment
        assert isinstance(risk_assessment["risk_factors"], list)
        assert isinstance(risk_assessment["recommendations"], list)
        
        # Validate company info structure
        company_info = data["company_info"]
        assert "kvk_number" in company_info
        assert "name" in company_info
        assert "status" in company_info


class TestPerformanceValidation:
    """Test performance requirements are met."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_standard_search_performance(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_info,
        mock_legal_cases,
        mock_news_analysis
    ):
        """Test that standard search completes within 30 seconds."""
        
        # Setup mocks with realistic delays
        async def delayed_kvk_response():
            await asyncio.sleep(0.5)  # Simulate API delay
            return mock_company_info
        
        async def delayed_legal_response():
            await asyncio.sleep(1.0)  # Simulate scraping delay
            return mock_legal_cases
        
        async def delayed_news_response():
            await asyncio.sleep(2.0)  # Simulate AI processing delay
            return mock_news_analysis
        
        mock_kvk_info.side_effect = delayed_kvk_response
        mock_legal_init.return_value = None
        mock_legal_search.side_effect = delayed_legal_response
        mock_news_search.side_effect = delayed_news_response
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            import time
            start_time = time.time()
            
            response = client.post(
                "/analyze-company",
                json={
                    "kvk_number": "69599084",
                    "search_depth": "standard"
                },
                headers={"X-API-Key": "test-api-key"}
            )
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Assertions
        assert response.status_code == 200
        assert total_time < 30.0, f"Standard search took {total_time}s, should be < 30s"
        
        data = response.json()
        assert data["processing_time_seconds"] < 30.0
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_deep_search_performance(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_info,
        mock_legal_cases,
        mock_news_analysis
    ):
        """Test that deep search completes within 60 seconds."""
        
        # Setup mocks with longer delays for deep search
        async def delayed_kvk_response():
            await asyncio.sleep(1.0)
            return mock_company_info
        
        async def delayed_legal_response():
            await asyncio.sleep(3.0)  # Longer for deep search
            return mock_legal_cases
        
        async def delayed_news_response():
            await asyncio.sleep(5.0)  # Longer AI processing
            return mock_news_analysis
        
        mock_kvk_info.side_effect = delayed_kvk_response
        mock_legal_init.return_value = None
        mock_legal_search.side_effect = delayed_legal_response  
        mock_news_search.side_effect = delayed_news_response
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            import time
            start_time = time.time()
            
            response = client.post(
                "/analyze-company",
                json={
                    "kvk_number": "69599084",
                    "search_depth": "deep"
                },
                headers={"X-API-Key": "test-api-key"}
            )
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Assertions
        assert response.status_code == 200
        assert total_time < 60.0, f"Deep search took {total_time}s, should be < 60s"
        
        data = response.json()
        assert data["processing_time_seconds"] < 60.0


class TestDataConsistency:
    """Test data consistency across services."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_risk_assessment_consistency(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_info,
        mock_legal_cases,
        mock_news_analysis
    ):
        """Test that risk assessment is consistent with input data."""
        
        # Create high-risk scenario
        high_risk_legal_cases = [
            LegalCase(
                case_id="HIGH_RISK_001",
                date=datetime.now() - timedelta(days=30),
                case_type="Criminal",
                summary="Fraud investigation ongoing",
                outcome="Under investigation",
                court="Rechtbank Amsterdam", 
                parties=["Test Company B.V.", "Public Prosecutor"]
            ),
            LegalCase(
                case_id="HIGH_RISK_002",
                date=datetime.now() - timedelta(days=60),
                case_type="Administrative",
                summary="Major regulatory violation with €100,000 fine",
                outcome="€100,000 penalty imposed",
                court="Administrative Court",
                parties=["Test Company B.V.", "Financial Authority"]
            )
        ]
        
        high_risk_news = NewsAnalysis(
            total_articles_found=15,
            total_relevance=0.9,
            overall_sentiment=-0.6,  # Very negative sentiment
            sentiment_summary={
                "positive": 10,
                "neutral": 20,
                "negative": 70
            },
            key_topics=[
                "Legal Issues",
                "Financial Concerns", 
                "Regulatory Issues",
                "Investigation"
            ],
            risk_indicators=[
                "fraud investigation",
                "regulatory violation",
                "financial penalty"
            ],
            positive_news={"count": 2, "themes": []},
            negative_news={"count": 10, "themes": ["fraud", "violation", "penalty"]},
            articles=[]
        )
        
        # Setup mocks
        mock_kvk_info.return_value = mock_company_info
        mock_legal_init.return_value = None
        mock_legal_search.return_value = high_risk_legal_cases
        mock_news_search.return_value = high_risk_news
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "69599084"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Risk assessment should reflect high risk
        risk_assessment = data["risk_assessment"]
        assert risk_assessment["overall_risk_level"] in ["HIGH", "CRITICAL"]
        assert risk_assessment["risk_score"] > 60  # Should be high risk score
        
        # Should have specific risk factors mentioned
        risk_factors = " ".join(risk_assessment["risk_factors"]).lower()
        assert "criminal" in risk_factors or "fraud" in risk_factors
        assert "negative" in risk_factors or "penalty" in risk_factors
        
        # Should have appropriate recommendations
        recommendations = " ".join(risk_assessment["recommendations"]).lower()
        assert "due diligence" in recommendations or "caution" in recommendations