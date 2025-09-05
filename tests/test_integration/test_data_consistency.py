"""
Integration tests for data consistency across services.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.models.responses import CompanyInfo, LegalCase, NewsAnalysis


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def consistent_company_info():
    """Company info for consistency testing."""
    return CompanyInfo(
        kvk_number="12345678",
        name="Consistent Test Company B.V.",
        trade_name="ConsistentCorp",
        status="Actief",
        establishment_date=datetime(2020, 1, 15),
        address="Consistency Street 123, 1000 AB Amsterdam",
        postal_code="1000AB",
        city="Amsterdam",
        country="Nederland",
        phone="+31 20 1234567",
        website="https://www.consistentcorp.nl",
        email="info@consistentcorp.nl",
        sbi_codes=["6201", "6202", "7020"],
        employee_count=50,
        legal_form="Besloten Vennootschap"
    )


class TestCrossServiceDataValidation:
    """Test data consistency between different services."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_company_name_consistency_across_services(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        consistent_company_info
    ):
        """Test that company names are consistent across all services."""
        
        # Setup legal cases with consistent company name
        legal_cases = [
            LegalCase(
                case_id="CONS001",
                date=datetime.now() - timedelta(days=90),
                case_type="Civiel",
                summary="Contract dispute involving Consistent Test Company B.V.",
                outcome="Settled out of court",
                court="Rechtbank Amsterdam",
                parties=["Consistent Test Company B.V.", "Other Party Ltd"]
            ),
            LegalCase(
                case_id="CONS002",
                date=datetime.now() - timedelta(days=180),
                case_type="Administratief", 
                summary="Regulatory matter for ConsistentCorp (trade name)",
                outcome="Resolved with warning",
                court="Administrative Court",
                parties=["ConsistentCorp", "Regulatory Authority"]
            )
        ]
        
        # Setup news analysis with consistent naming
        news_analysis = NewsAnalysis(
            total_articles_found=12,
            total_relevance=0.88,
            overall_sentiment=0.3,
            sentiment_summary={"positive": 60, "neutral": 30, "negative": 10},
            key_topics=["Business Growth", "Innovation", "Partnership"],
            risk_indicators=[],
            positive_news={"count": 7, "themes": ["growth", "innovation"]},
            negative_news={"count": 1, "themes": ["minor complaint"]},
            articles=[
                {
                    "title": "Consistent Test Company B.V. Announces Growth",
                    "summary": "ConsistentCorp expands operations in Amsterdam",
                    "date": "2024-01-20",
                    "sentiment": 0.6,
                    "relevance": 0.9
                }
            ]
        )
        
        # Setup mocks
        mock_kvk_info.return_value = consistent_company_info
        mock_legal_init.return_value = None
        mock_legal_search.return_value = legal_cases
        mock_news_search.return_value = news_analysis
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "12345678"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify name consistency
        company_name = data["company_info"]["name"]
        trade_name = data["company_info"]["trade_name"]
        
        # Check legal cases reference the same company
        for case in data["legal_findings"]["cases"]:
            case_parties = " ".join(case["parties"])
            assert (company_name in case_parties or 
                   trade_name in case_parties), f"Company name not found in legal case: {case_parties}"
        
        # Check news articles reference the same company
        for article in data["news_analysis"]["articles"]:
            article_text = article["title"] + " " + article["summary"]
            assert (company_name in article_text or 
                   trade_name in article_text), f"Company name not found in news article: {article_text}"
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_legal_case_date_validation(
        self,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        consistent_company_info
    ):
        """Test that legal case dates are reasonable and consistent."""
        
        # Create legal cases with various dates
        legal_cases = [
            LegalCase(
                case_id="DATE001",
                date=datetime.now() - timedelta(days=30),  # Recent
                case_type="Civiel",
                summary="Recent case",
                outcome="Pending",
                court="Rechtbank Amsterdam",
                parties=["Consistent Test Company B.V.", "Recent Party"]
            ),
            LegalCase(
                case_id="DATE002", 
                date=datetime.now() - timedelta(days=365 * 2),  # 2 years ago
                case_type="Administratief",
                summary="Older case",
                outcome="Resolved",
                court="Administrative Court",
                parties=["Consistent Test Company B.V.", "Authority"]
            ),
            # Edge case: very old case (should still be valid but noted)
            LegalCase(
                case_id="DATE003",
                date=datetime.now() - timedelta(days=365 * 10),  # 10 years ago
                case_type="Civiel",
                summary="Very old case",
                outcome="Closed",
                court="Rechtbank Amsterdam", 
                parties=["Consistent Test Company B.V.", "Old Party"]
            )
        ]
        
        mock_kvk_info.return_value = consistent_company_info
        mock_legal_init.return_value = None
        mock_legal_search.return_value = legal_cases
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                response = client.post(
                    "/analyze-company",
                    json={"kvk_number": "12345678"},
                    headers={"X-API-Key": "test-api-key"}
                )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all case dates are reasonable
        company_establishment = datetime(2020, 1, 15)
        
        for case in data["legal_findings"]["cases"]:
            case_date = datetime.fromisoformat(case["date"].replace('Z', '+00:00')).replace(tzinfo=None)
            
            # Case should not be in the future
            assert case_date <= datetime.now(), f"Case date in future: {case_date}"
            
            # Case should not be before company establishment (with some buffer)
            buffer_date = company_establishment - timedelta(days=365)  # 1 year buffer
            assert case_date >= buffer_date, f"Case date too far before establishment: {case_date}"
        
        # Risk assessment should consider case recency
        risk_factors = " ".join(data["risk_assessment"]["risk_factors"]).lower()
        if len(legal_cases) > 0:
            # Should mention recent activity if there are recent cases
            recent_cases = [c for c in legal_cases if c.date > datetime.now() - timedelta(days=365 * 2)]
            if recent_cases:
                assert "recent" in risk_factors or "within" in risk_factors


class TestRiskAssessmentAccuracy:
    """Test accuracy and consistency of risk assessments."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_risk_level_consistency_with_data(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client
    ):
        """Test that risk levels are consistent with underlying data."""
        
        # Test low risk scenario
        low_risk_company = CompanyInfo(
            kvk_number="12345678",
            name="Low Risk Company B.V.",
            trade_name="LowRiskCorp",
            status="Actief",
            establishment_date=datetime.now() - timedelta(days=365 * 5),  # 5 years old
            address="Safe Street 1, 1000 AB Amsterdam",
            postal_code="1000AB",
            city="Amsterdam",
            country="Nederland",
            sbi_codes=["6201"],  # Standard business activity
            employee_count=25,
            legal_form="BV"
        )
        
        # No legal cases
        legal_cases = []
        
        # Positive news
        positive_news = NewsAnalysis(
            total_articles_found=5,
            total_relevance=0.8,
            overall_sentiment=0.4,  # Positive sentiment
            sentiment_summary={"positive": 70, "neutral": 25, "negative": 5},
            key_topics=["Innovation", "Growth", "Partnership"],
            risk_indicators=[],
            positive_news={"count": 4, "themes": ["growth", "innovation"]},
            negative_news={"count": 0, "themes": []},
            articles=[]
        )
        
        mock_kvk_info.return_value = low_risk_company
        mock_legal_init.return_value = None
        mock_legal_search.return_value = legal_cases
        mock_news_search.return_value = positive_news
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "12345678"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be low risk
        risk_level = data["risk_assessment"]["overall_risk_level"]
        assert risk_level in ["LOW", "MEDIUM"], f"Expected LOW or MEDIUM risk, got {risk_level}"
        
        risk_score = data["risk_assessment"]["risk_score"]
        assert risk_score < 50, f"Expected low risk score, got {risk_score}"
        
        # Should have positive factors mentioned
        positive_factors = data["risk_assessment"].get("positive_factors", [])
        risk_factors = data["risk_assessment"]["risk_factors"]
        
        # More positive than negative indicators
        assert len(positive_factors) + len([f for f in risk_factors if "active" in f.lower() or "positive" in f.lower()]) > 0
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_high_risk_scenario_consistency(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client
    ):
        """Test high risk scenario produces consistent assessment."""
        
        # High risk company profile
        high_risk_company = CompanyInfo(
            kvk_number="87654321",
            name="High Risk Company B.V.",
            trade_name="RiskyCorp",
            status="Niet actief",  # Inactive status
            establishment_date=datetime.now() - timedelta(days=90),  # Very new
            address="Risk Avenue 666, 6666 ZZ Risktown",
            postal_code="6666ZZ",
            city="Risktown",
            country="Nederland",
            sbi_codes=[],  # No business activities
            employee_count=0,  # No employees
            legal_form="BV"
        )
        
        # Multiple serious legal cases
        high_risk_legal_cases = [
            LegalCase(
                case_id="RISK001",
                date=datetime.now() - timedelta(days=30),
                case_type="Criminal",
                summary="Fraud investigation ongoing with €500,000 damages",
                outcome="Under investigation",
                court="Rechtbank Amsterdam",
                parties=["High Risk Company B.V.", "Public Prosecutor"]
            ),
            LegalCase(
                case_id="RISK002",
                date=datetime.now() - timedelta(days=60),
                case_type="Administrative",
                summary="Major regulatory violation with €250,000 fine imposed",
                outcome="€250,000 penalty",
                court="Administrative Court",
                parties=["RiskyCorp", "Financial Authority"]
            ),
            LegalCase(
                case_id="RISK003",
                date=datetime.now() - timedelta(days=45),
                case_type="Civiel",
                summary="Bankruptcy proceedings initiated by creditors",
                outcome="Proceedings ongoing",
                court="Rechtbank Amsterdam",
                parties=["High Risk Company B.V.", "Creditor Consortium"]
            )
        ]
        
        # Highly negative news
        negative_news = NewsAnalysis(
            total_articles_found=20,
            total_relevance=0.95,
            overall_sentiment=-0.7,  # Very negative
            sentiment_summary={"positive": 5, "neutral": 15, "negative": 80},
            key_topics=["Fraud Investigation", "Regulatory Violation", "Bankruptcy", "Legal Issues"],
            risk_indicators=["fraud", "bankruptcy", "violation", "investigation"],
            positive_news={"count": 1, "themes": []},
            negative_news={"count": 16, "themes": ["fraud", "bankruptcy", "violation"]},
            articles=[]
        )
        
        mock_kvk_info.return_value = high_risk_company
        mock_legal_init.return_value = None
        mock_legal_search.return_value = high_risk_legal_cases
        mock_news_search.return_value = negative_news
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "87654321"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be high or critical risk
        risk_level = data["risk_assessment"]["overall_risk_level"]
        assert risk_level in ["HIGH", "CRITICAL"], f"Expected HIGH or CRITICAL risk, got {risk_level}"
        
        risk_score = data["risk_assessment"]["risk_score"]
        assert risk_score >= 60, f"Expected high risk score (>=60), got {risk_score}"
        
        # Should have multiple risk factors
        risk_factors = data["risk_assessment"]["risk_factors"]
        assert len(risk_factors) >= 5, f"Expected multiple risk factors, got {len(risk_factors)}"
        
        # Should mention specific risks
        risk_text = " ".join(risk_factors).lower()
        assert any(keyword in risk_text for keyword in ["criminal", "fraud", "inactive", "bankruptcy"])
        
        # Should have serious recommendations
        recommendations = data["risk_assessment"]["recommendations"]
        assert len(recommendations) >= 3, f"Expected multiple recommendations, got {len(recommendations)}"
        
        rec_text = " ".join(recommendations).lower()
        assert any(keyword in rec_text for keyword in ["caution", "due diligence", "avoid", "extreme"])


class TestResponseCompletenessChecks:
    """Test that responses are complete and well-formed."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_complete_response_structure(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        consistent_company_info
    ):
        """Test that complete responses have all required fields."""
        
        # Setup full data scenario
        legal_cases = [
            LegalCase(
                case_id="COMP001",
                date=datetime.now() - timedelta(days=60),
                case_type="Civiel",
                summary="Complete test case",
                outcome="Resolved",
                court="Rechtbank Amsterdam",
                parties=["Consistent Test Company B.V.", "Test Party"]
            )
        ]
        
        news_analysis = NewsAnalysis(
            total_articles_found=10,
            total_relevance=0.8,
            overall_sentiment=0.1,
            sentiment_summary={"positive": 50, "neutral": 30, "negative": 20},
            key_topics=["Business", "Operations"],
            risk_indicators=[],
            positive_news={"count": 5, "themes": ["growth"]},
            negative_news={"count": 2, "themes": ["complaint"]},
            articles=[
                {
                    "title": "Complete Test Article",
                    "summary": "Full article summary",
                    "date": "2024-01-15",
                    "sentiment": 0.2,
                    "relevance": 0.8
                }
            ]
        )
        
        mock_kvk_info.return_value = consistent_company_info
        mock_legal_init.return_value = None
        mock_legal_search.return_value = legal_cases
        mock_news_search.return_value = news_analysis
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={"kvk_number": "12345678"},
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level completeness
        required_top_level = [
            "request_id", "analysis_timestamp", "processing_time_seconds",
            "company_info", "legal_findings", "news_analysis",
            "risk_assessment", "warnings", "data_sources"
        ]
        
        for field in required_top_level:
            assert field in data, f"Missing top-level field: {field}"
        
        # Check company_info completeness
        company_info = data["company_info"]
        required_company_fields = [
            "kvk_number", "name", "status", "address", "city", "country"
        ]
        
        for field in required_company_fields:
            assert field in company_info, f"Missing company_info field: {field}"
            assert company_info[field] is not None, f"Company_info field is null: {field}"
        
        # Check legal_findings completeness
        legal_findings = data["legal_findings"]
        assert "total_cases" in legal_findings
        assert "cases" in legal_findings
        assert len(legal_findings["cases"]) == legal_findings["total_cases"]
        
        # Check each legal case completeness
        for case in legal_findings["cases"]:
            required_case_fields = ["case_id", "date", "case_type", "summary", "court", "parties"]
            for field in required_case_fields:
                assert field in case, f"Missing legal case field: {field}"
        
        # Check news_analysis completeness
        news = data["news_analysis"]
        required_news_fields = [
            "total_articles_found", "overall_sentiment", "sentiment_summary",
            "key_topics", "positive_news", "negative_news"
        ]
        
        for field in required_news_fields:
            assert field in news, f"Missing news_analysis field: {field}"
        
        # Check risk_assessment completeness
        risk = data["risk_assessment"]
        required_risk_fields = [
            "overall_risk_level", "risk_score", "risk_factors", "recommendations"
        ]
        
        for field in required_risk_fields:
            assert field in risk, f"Missing risk_assessment field: {field}"
        
        # Check that lists are not empty where they shouldn't be
        assert len(data["data_sources"]) >= 1, "data_sources should not be empty"
        assert isinstance(data["warnings"], list), "warnings should be a list"


class TestDataFreshnessValidation:
    """Test validation of data freshness and temporal consistency."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases') 
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_data_freshness_indicators(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        consistent_company_info
    ):
        """Test that data freshness is properly indicated in responses."""
        
        # Mix of old and recent data
        legal_cases = [
            LegalCase(
                case_id="FRESH001",
                date=datetime.now() - timedelta(days=30),  # Fresh
                case_type="Civiel",
                summary="Recent case",
                outcome="Resolved",
                court="Rechtbank Amsterdam",
                parties=["Consistent Test Company B.V.", "Recent Party"]
            ),
            LegalCase(
                case_id="OLD001",
                date=datetime.now() - timedelta(days=365 * 3),  # 3 years old
                case_type="Administratief",
                summary="Old case from 3 years ago",
                outcome="Resolved",
                court="Administrative Court",
                parties=["Consistent Test Company B.V.", "Old Authority"]
            )
        ]
        
        news_analysis = NewsAnalysis(
            total_articles_found=8,
            total_relevance=0.75,
            overall_sentiment=0.2,
            sentiment_summary={"positive": 55, "neutral": 30, "negative": 15},
            key_topics=["Recent Developments", "Historical Context"],
            risk_indicators=[],
            positive_news={"count": 4, "themes": ["recent growth"]},
            negative_news={"count": 1, "themes": ["old complaint"]},
            articles=[
                {
                    "title": "Recent Company News",
                    "summary": "Fresh developments at the company",
                    "date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                    "sentiment": 0.4,
                    "relevance": 0.9
                },
                {
                    "title": "Older Company Update",
                    "summary": "Historical company information",
                    "date": (datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d"), 
                    "sentiment": 0.1,
                    "relevance": 0.6
                }
            ]
        )
        
        mock_kvk_info.return_value = consistent_company_info
        mock_legal_init.return_value = None
        mock_legal_search.return_value = legal_cases
        mock_news_search.return_value = news_analysis
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            response = client.post(
                "/analyze-company",
                json={
                    "kvk_number": "12345678",
                    "date_range": "1y"  # Request recent data
                },
                headers={"X-API-Key": "test-api-key"}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Risk assessment should consider data freshness
        risk_factors = data["risk_assessment"]["risk_factors"]
        risk_text = " ".join(risk_factors).lower()
        
        # Should differentiate between recent and old data
        if len(legal_cases) > 1:
            # Should mention recent activity if present
            recent_case_count = len([c for c in legal_cases if c.date > datetime.now() - timedelta(days=365)])
            if recent_case_count > 0:
                assert any("recent" in factor.lower() for factor in risk_factors), "Should mention recent legal activity"
        
        # News analysis should reflect recency 
        articles = data["news_analysis"]["articles"]
        if len(articles) > 1:
            dates = [datetime.fromisoformat(article["date"]) for article in articles]
            most_recent = max(dates)
            
            # Most recent article should be reasonably fresh for a 1y search
            assert most_recent > datetime.now() - timedelta(days=400), "Most recent article should be relatively fresh"