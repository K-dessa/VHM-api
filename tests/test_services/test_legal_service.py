"""
Tests for Legal Service.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from datetime import datetime
from bs4 import BeautifulSoup

from app.services.legal_service import LegalService
from app.models.response_models import LegalCase
from app.utils.text_utils import normalize_company_name, calculate_similarity, match_company_variations
from app.utils.web_utils import is_path_allowed, get_crawl_delay


@pytest.fixture
def legal_service():
    """Create Legal service instance for testing."""
    with patch('app.services.legal_service.settings') as mock_settings:
        mock_settings.APP_NAME = "test-app"
        mock_settings.RECHTSPRAAK_TIMEOUT = 30
        service = LegalService()
        service.robots_allowed = True  # Skip robots.txt check for tests
        return service


@pytest.fixture
def mock_search_html():
    """Sample HTML from rechtspraak.nl search results."""
    return """
    <html>
    <body>
        <div class="search-results">
            <div class="search-result">
                <h3><a href="/Uitspraken/12345">Test Company B.V. tegen gemeente Amsterdam</a></h3>
                <p class="datum">15-03-2023</p>
                <p class="rechtbank">Rechtbank Amsterdam</p>
                <p class="samenvatting">Geschil betreffende bouwvergunning...</p>
            </div>
            <div class="search-result">
                <h3><a href="/Uitspraken/67890">Stichting X tegen Test Company B.V.</a></h3>
                <p class="datum">22-01-2023</p>
                <p class="rechtbank">Gerechtshof Den Haag</p>
                <p class="samenvatting">Contractgeschil aangaande leveringsvoorwaarden...</p>
            </div>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_case_detail_html():
    """Sample HTML from a rechtspraak.nl case detail page."""
    return """
    <html>
    <body>
        <div class="uitspraak-header">
            <h1>Rechtbank Amsterdam</h1>
            <p>ECLI:NL:RBAMS:2023:1234</p>
            <p>Zaaknummer: 12345/2023</p>
        </div>
        <div class="partijen">
            <p>Eisers: Test Company B.V.</p>
            <p>Verweerder: Gemeente Amsterdam</p>
        </div>
        <div class="uitspraak-content">
            <p>De rechtbank oordeelt als volgt...</p>
            <p>Test Company B.V. heeft onvoldoende bewijs geleverd...</p>
            <p>Het verzoek wordt afgewezen.</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_robots_txt():
    """Sample robots.txt content."""
    return """
User-agent: *
Allow: /Uitspraken/
Disallow: /admin/
Disallow: /private/
Crawl-delay: 1

User-agent: test-bot
Disallow: /
    """


class TestLegalService:
    """Test cases for LegalService."""

    @pytest.mark.asyncio
    async def test_initialization(self, legal_service):
        """Test service initialization."""
        assert legal_service.base_url == "https://www.rechtspraak.nl"
        assert legal_service.rate_limit_delay == 1.0
        assert legal_service.robots_allowed is True

    @pytest.mark.asyncio
    async def test_robots_compliance_check(self, legal_service):
        """Test robots.txt compliance checking."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = """
User-agent: *
Allow: /Uitspraken/
Crawl-delay: 2
            """
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            await legal_service._check_robots_compliance()
            
            assert legal_service.robots_allowed is True
            assert legal_service.crawl_delay == 2.0

    @pytest.mark.asyncio
    async def test_cache_functionality(self, legal_service):
        """Test caching mechanism."""
        # Test cache miss
        cache_key = legal_service._get_cache_key("Test Company", "Test Trade")
        cached_result = legal_service._get_from_cache(cache_key)
        assert cached_result is None
        
        # Test cache set and hit
        test_data = [{"test": "data"}]
        legal_service._set_cache(cache_key, test_data, 3600)
        cached_result = legal_service._get_from_cache(cache_key)
        assert cached_result == test_data

    @pytest.mark.asyncio
    async def test_search_company_cases_cached(self, legal_service):
        """Test search with cached results."""
        test_cases = [
            LegalCase(
                ecli="ECLI:NL:RBAMS:2023:1234",
                case_number="12345/2023",
                date=datetime(2023, 3, 15),
                court="Rechtbank Amsterdam",
                type="civil",
                parties=["Test Company B.V."],
                summary="Test case summary",
                outcome="unknown",
                url="https://www.rechtspraak.nl/Uitspraken/12345",
                relevance_score=0.9
            )
        ]
        
        # Set up cache
        cache_key = legal_service._get_cache_key("Test Company B.V.")
        legal_service._set_cache(cache_key, test_cases, 3600)
        
        # Test cached retrieval
        results = await legal_service.search_company_cases("Test Company B.V.")
        assert len(results) == 1
        assert results[0].ecli == "ECLI:NL:RBAMS:2023:1234"

    @pytest.mark.asyncio
    async def test_search_company_cases_no_robots(self, legal_service):
        """Test search when robots.txt disallows."""
        legal_service.robots_allowed = False
        
        results = await legal_service.search_company_cases("Test Company")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_search_page(self, legal_service, mock_search_html):
        """Test fetching search page HTML."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = mock_search_html
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await legal_service._fetch_search_page({'q': 'Test Company'})
            assert result == mock_search_html

    @pytest.mark.asyncio
    async def test_fetch_search_page_error(self, legal_service):
        """Test handling of search page fetch errors."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 500
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await legal_service._fetch_search_page({'q': 'Test Company'})
            assert result == ""

    def test_parse_search_results(self, legal_service, mock_search_html):
        """Test parsing search results HTML."""
        results = legal_service._parse_search_results(mock_search_html)
        
        assert len(results) == 2
        assert "Test Company B.V." in results[0]['title']
        assert "/Uitspraken/12345" in results[0]['url']
        assert "15-03-2023" in results[0]['date_text']
        assert "Rechtbank Amsterdam" in results[0]['court_text']

    def test_parse_search_results_empty(self, legal_service):
        """Test parsing empty search results."""
        empty_html = "<html><body>No results found</body></html>"
        results = legal_service._parse_search_results(empty_html)
        assert results == []

    def test_extract_case_from_element(self, legal_service):
        """Test extracting case information from HTML element."""
        html = """
        <div class="search-result">
            <h3><a href="/Uitspraken/12345">Test Company B.V. vs City</a></h3>
            <p>12-03-2023</p>
            <p>Rechtbank Amsterdam</p>
            <p class="summary">Contract dispute case</p>
        </div>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        element = soup.find('div', class_='search-result')
        
        result = legal_service._extract_case_from_element(element)
        
        assert result is not None
        assert "/Uitspraken/12345" in result['url']
        assert "Test Company B.V." in result['title']

    @pytest.mark.asyncio
    async def test_get_case_details(self, legal_service, mock_case_detail_html):
        """Test fetching case details."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = mock_case_detail_html
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await legal_service.get_case_details("https://www.rechtspraak.nl/Uitspraken/12345")
            
            assert result is not None
            assert result['ecli'] == "ECLI:NL:RBAMS:2023:1234"
            assert result['case_number'] == "12345/2023"
            assert "Test Company B.V." in result['parties']

    def test_parse_case_detail(self, legal_service, mock_case_detail_html):
        """Test parsing case detail HTML."""
        result = legal_service._parse_case_detail(
            mock_case_detail_html, 
            "https://www.rechtspraak.nl/Uitspraken/12345"
        )
        
        assert result['ecli'] == "ECLI:NL:RBAMS:2023:1234"
        assert result['case_number'] == "12345/2023"
        assert len(result['parties']) > 0

    def test_deduplicate_cases(self, legal_service):
        """Test case deduplication."""
        cases = [
            {'url': 'https://example.com/case1', 'ecli': 'ECLI:NL:TEST:2023:001'},
            {'url': 'https://example.com/case1', 'ecli': 'ECLI:NL:TEST:2023:001'},  # Duplicate URL
            {'url': 'https://example.com/case2', 'ecli': 'ECLI:NL:TEST:2023:002'},
        ]
        
        unique_cases = legal_service._deduplicate_cases(cases)
        assert len(unique_cases) == 2

    def test_calculate_relevance_score(self, legal_service):
        """Test relevance score calculation."""
        case_data = {
            'title': 'Test Company B.V. tegen gemeente',
            'summary': 'Geschil over bouwvergunning voor Test Company B.V.',
            'parties': ['Test Company B.V.', 'Gemeente Amsterdam']
        }
        
        score = legal_service._calculate_relevance_score(case_data, "Test Company B.V.")
        assert score >= 0.8  # Should be high relevance

    def test_calculate_relevance_score_low(self, legal_service):
        """Test low relevance score calculation."""
        case_data = {
            'title': 'Unrelated Company vs Another Party',
            'summary': 'Case about something unrelated',
            'parties': ['Other Company B.V.', 'Different Party']
        }
        
        score = legal_service._calculate_relevance_score(case_data, "Test Company B.V.")
        assert score < 0.6  # Should be low relevance

    def test_convert_to_legal_case(self, legal_service):
        """Test converting case data to LegalCase object."""
        case_data = {
            'url': 'https://www.rechtspraak.nl/Uitspraken/12345',
            'title': 'Test Company B.V. vs City',
            'date_text': '15-03-2023',
            'court_text': 'Rechtbank Amsterdam',
            'summary': 'Contract dispute case',
            'ecli': 'ECLI:NL:RBAMS:2023:1234',
            'case_number': '12345/2023',
            'parties': ['Test Company B.V.', 'City of Amsterdam']
        }
        
        legal_case = legal_service._convert_to_legal_case(case_data, 0.9)
        
        assert legal_case is not None
        assert legal_case.ecli == 'ECLI:NL:RBAMS:2023:1234'
        assert legal_case.case_number == '12345/2023'
        assert legal_case.court == 'Rechtbank Amsterdam'
        assert legal_case.relevance_score == 0.9

    def test_convert_to_legal_case_no_ecli(self, legal_service):
        """Test converting case data without ECLI."""
        case_data = {
            'url': 'https://www.rechtspraak.nl/Uitspraken/12345',
            'title': 'Test Company B.V. vs City',
            'date_text': '15-03-2023',
            'court_text': 'Rechtbank Amsterdam',
            'summary': 'Contract dispute case',
            'case_number': '12345/2023',
            'parties': ['Test Company B.V.']
        }
        
        legal_case = legal_service._convert_to_legal_case(case_data, 0.8)
        
        assert legal_case is not None
        assert legal_case.ecli.startswith('ECLI:NL:PLACEHOLDER:')
        assert legal_case.case_number == '12345/2023'

    def test_determine_case_type(self, legal_service):
        """Test case type determination."""
        # Criminal case
        criminal_case = {
            'title': 'Strafzaak tegen verdachte',
            'summary': 'Strafrecht procedure',
            'court_text': 'Rechtbank'
        }
        assert legal_service._determine_case_type(criminal_case) == 'criminal'
        
        # Administrative case
        admin_case = {
            'title': 'Bestuursrecht zaak',
            'summary': 'Geschil met gemeente',
            'court_text': 'Rechtbank'
        }
        assert legal_service._determine_case_type(admin_case) == 'administrative'
        
        # Civil case (default)
        civil_case = {
            'title': 'Contract geschil',
            'summary': 'Burgerlijk recht',
            'court_text': 'Rechtbank'
        }
        assert legal_service._determine_case_type(civil_case) == 'civil'

    def test_assess_legal_risk_no_cases(self, legal_service):
        """Test risk assessment with no cases."""
        risk_level = legal_service.assess_legal_risk([])
        assert risk_level == 'low'

    def test_assess_legal_risk_low(self, legal_service):
        """Test low risk assessment."""
        cases = [
            LegalCase(
                ecli="ECLI:NL:RBAMS:2020:1234",
                case_number="12345/2020",
                date=datetime(2020, 3, 15),  # Old case
                court="Rechtbank Amsterdam",
                type="civil",
                parties=["Test Company B.V."],
                summary="Old civil case",
                outcome="won",
                url="https://www.rechtspraak.nl/Uitspraken/12345",
                relevance_score=0.8
            )
        ]
        
        risk_level = legal_service.assess_legal_risk(cases)
        assert risk_level == 'low'

    def test_assess_legal_risk_high(self, legal_service):
        """Test high risk assessment."""
        cases = []
        # Create multiple recent criminal cases
        for i in range(3):
            case = LegalCase(
                ecli=f"ECLI:NL:RBAMS:2023:{1234+i}",
                case_number=f"{12345+i}/2023",
                date=datetime(2023, 3, 15),  # Recent
                court="Rechtbank Amsterdam",
                type="criminal",  # Criminal type
                parties=["Test Company B.V."],
                summary=f"Criminal case {i+1}",
                outcome="lost",
                url=f"https://www.rechtspraak.nl/Uitspraken/{12345+i}",
                relevance_score=0.9
            )
            cases.append(case)
        
        risk_level = legal_service.assess_legal_risk(cases)
        assert risk_level == 'high'

    @pytest.mark.asyncio
    async def test_rate_limiting(self, legal_service):
        """Test rate limiting enforcement."""
        import time
        
        start_time = time.time()
        legal_service.last_request_time = start_time
        
        await legal_service._enforce_rate_limit()
        await legal_service._enforce_rate_limit()
        
        elapsed = time.time() - start_time
        assert elapsed >= legal_service.crawl_delay


class TestTextUtils:
    """Test cases for text utility functions."""

    def test_normalize_company_name(self):
        """Test company name normalization."""
        assert normalize_company_name("Test Company B.V.") == "test company bv"
        assert normalize_company_name("Besloten Vennootschap Test") == "bv test"
        assert normalize_company_name("De Test Company N.V.") == "test company nv"

    def test_calculate_similarity(self):
        """Test similarity calculation."""
        assert calculate_similarity("Test Company B.V.", "Test Company BV") > 0.9
        assert calculate_similarity("Test Company", "Different Company") < 0.5
        assert calculate_similarity("", "Test") == 0.0

    def test_match_company_variations(self):
        """Test company name variation matching."""
        text = "In deze zaak tussen Test Company B.V. en de gemeente..."
        assert match_company_variations(text, "Test Company B.V.") is True
        assert match_company_variations(text, "Different Company") is False
        assert match_company_variations(text, "Test Company") is True  # Partial match


class TestWebUtils:
    """Test cases for web utility functions."""

    def test_is_path_allowed(self):
        """Test robots.txt path checking."""
        robots_txt = """
User-agent: *
Allow: /Uitspraken/
Disallow: /admin/
        """
        
        assert is_path_allowed("/Uitspraken/12345", "*", robots_txt) is True
        assert is_path_allowed("/admin/secret", "*", robots_txt) is False
        assert is_path_allowed("/public/page", "*", robots_txt) is True  # Not disallowed

    def test_get_crawl_delay(self):
        """Test crawl delay extraction."""
        robots_txt = """
User-agent: *
Crawl-delay: 2
        """
        
        assert get_crawl_delay(robots_txt, "*") == 2
        assert get_crawl_delay(robots_txt, "test-bot") == 2  # Falls back to *
        assert get_crawl_delay("", "*") is None