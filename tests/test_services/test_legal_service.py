import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.services.legal_service import LegalService
from app.models.response_models import LegalCase
from app.utils.text_utils import (
    normalize_company_name,
    calculate_similarity,
    match_company_variations,
)
from app.utils.web_utils import is_path_allowed, get_crawl_delay


@pytest.fixture
def legal_service():
    """Create a LegalService instance for testing."""
    with patch("app.services.legal_service.settings") as mock_settings:
        mock_settings.APP_NAME = "test-app"
        mock_settings.RECHTSPRAAK_TIMEOUT = 30
        service = LegalService()
        return service


@pytest.mark.asyncio
async def test_fetch_api_search_atom_success(legal_service):
    """_fetch_api_search returns raw XML when Atom feed is received."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/atom+xml"}
        mock_resp.text = "<feed></feed>"
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_resp

        result = await legal_service._fetch_api_search({"max": 10})
        assert result == "<feed></feed>"


@pytest.mark.asyncio
async def test_fetch_api_search_failure(legal_service):
    """LegalService._fetch_api_search returns None on HTTP errors."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_resp

        result = await legal_service._fetch_api_search({"max": 10})
        assert result is None


@pytest.mark.asyncio
async def test_extract_case_from_api_data(legal_service):
    """Case details are fetched and merged into result."""
    case_data = {
        "identifier": "ECLI:NL:RBAMS:2023:1234",
        "title": "Test vs Gemeente",
        "date": "2023-03-15",
        "spatial": "Rechtbank Amsterdam",
        "type": "civil",
    }

    with patch.object(
        LegalService,
        "_fetch_case_details",
        new=AsyncMock(return_value={
            "full_text": "content",
            "parties": ["Test Company B.V."],
            "case_number": "12345",
            "summary": "Samenvatting",
        }),
    ):
        result = await legal_service._extract_case_from_api_data(case_data)

    assert result["ecli"] == "ECLI:NL:RBAMS:2023:1234"
    assert result["case_number"] == "12345"
    assert result["summary"] == "Samenvatting"


@pytest.mark.asyncio
async def test_parse_api_results_atom(legal_service):
    """Atom XML responses are parsed into case dictionaries."""
    atom_xml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry>"
        "<id>ECLI:NL:RBAMS:2023:1234</id>"
        "<title>ECLI:NL:RBAMS:2023:1234, Rechtbank Amsterdam, 15-03-2023, Titel</title>"
        "<summary>Samenvatting</summary>"
        "<updated>2023-03-16T12:00:00Z</updated>"
        "<link rel='alternate' href='https://uitspraken.rechtspraak.nl/details?id=ECLI:NL:RBAMS:2023:1234'/></entry>"
        "</feed>"
    )

    with patch.object(LegalService, "_fetch_case_details", new=AsyncMock(return_value={})):  # avoid extra HTTP
        results = await legal_service._parse_api_results(atom_xml)

    assert len(results) == 1
    case = results[0]
    assert case["ecli"] == "ECLI:NL:RBAMS:2023:1234"
    assert case["court_text"] == "Rechtbank Amsterdam"
    assert case["date_text"] == "15-03-2023"

@pytest.mark.asyncio
async def test_search_company_cases_cached(legal_service):
    """Cached results are returned without API calls."""
    case = LegalCase(
        ecli="ECLI:NL:RBAMS:2023:1234",
        case_number="12345/2023",
        date=datetime(2023, 3, 15),
        court="Rechtbank Amsterdam",
        type="civil",
        parties=["Test Company B.V."],
        summary="Test case summary",
        outcome="unknown",
        url="https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:RBAMS:2023:1234",
        relevance_score=0.9,
    )

    cache_key = legal_service._get_cache_key("Test Company B.V.")
    legal_service._set_cache(cache_key, [case], 3600)

    results = await legal_service.search_company_cases("Test Company B.V.")

    assert len(results) == 1
    assert results[0].ecli == "ECLI:NL:RBAMS:2023:1234"


@pytest.mark.asyncio
async def test_search_company_cases_api(legal_service):
    """API results are converted into LegalCase objects."""
    sample_case = {
        "ecli": "ECLI:NL:RBAMS:2023:1234",
        "case_number": "12345/2023",
        "date_text": "2023-03-15",
        "court_text": "Rechtbank Amsterdam",
        "case_type": "civil",
        "parties": ["Test Company B.V."],
        "summary": "Test case summary",
        "url": "https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:RBAMS:2023:1234",
    }

    with patch.object(
        LegalService, "_perform_search", new=AsyncMock(return_value=[sample_case])
    ):
        results = await legal_service.search_company_cases("Test Company B.V.")

    assert len(results) == 1
    assert isinstance(results[0], LegalCase)


def test_deduplicate_cases(legal_service):
    """Duplicate cases are removed based on URL/ECLI."""
    cases = [
        {"url": "https://example.com/1", "ecli": "ECLI:NL:TEST:1"},
        {"url": "https://example.com/1", "ecli": "ECLI:NL:TEST:1"},
        {"url": "https://example.com/2", "ecli": "ECLI:NL:TEST:2"},
    ]

    unique = legal_service._deduplicate_cases(cases)
    assert len(unique) == 2


def test_calculate_relevance_score(legal_service):
    """Relevance score is high for matching company names."""
    case_data = {
        "title": "Test Company B.V. tegen gemeente",
        "summary": "Geschil over bouwvergunning voor Test Company B.V.",
        "parties": ["Test Company B.V.", "Gemeente Amsterdam"],
    }

    score = legal_service._calculate_relevance_score(
        case_data, "Test Company B.V."
    )
    assert score >= 0.8


def test_assess_legal_risk_high(legal_service):
    """Multiple recent criminal cases result in high risk."""
    cases = []
    for i in range(3):
        cases.append(
            LegalCase(
                ecli=f"ECLI:NL:RBAMS:2023:{1234 + i}",
                case_number=f"{12345 + i}/2023",
                date=datetime(2023, 3, 15),
                court="Rechtbank Amsterdam",
                type="criminal",
                parties=["Test Company"],
                summary="Case",
                outcome="lost",
                url=f"https://data.rechtspraak.nl/{12345 + i}",
                relevance_score=0.9,
            )
        )

    risk = legal_service.assess_legal_risk(cases)
    assert risk == "high"


class TestTextUtils:
    """Tests for text utility functions."""

    def test_normalize_company_name(self):
        assert normalize_company_name("Test Company B.V.") == "test company bv"
        assert normalize_company_name("Besloten Vennootschap Test") == "bv test"
        assert normalize_company_name("De Test Company N.V.") == "test company nv"

    def test_calculate_similarity(self):
        assert calculate_similarity("Test Company B.V.", "Test Company BV") > 0.9
        assert calculate_similarity("Test Company", "Different Company") < 0.6
        assert calculate_similarity("", "Test") == 0.0

    def test_match_company_variations(self):
        text = "In deze zaak tussen Test Company B.V. en de gemeente..."
        assert match_company_variations(text, "Test Company B.V.") is True
        assert match_company_variations(text, "Different Company") is False
        assert match_company_variations(text, "Test Company") is True


class TestWebUtils:
    """Tests for robots.txt utility helpers."""

    def test_is_path_allowed(self):
        robots_txt = """
User-agent: *
Allow: /Uitspraken/
Disallow: /admin/
        """
        assert is_path_allowed("/Uitspraken/12345", "*", robots_txt) is True
        assert is_path_allowed("/admin/secret", "*", robots_txt) is False
        assert is_path_allowed("/public/page", "*", robots_txt) is True

    def test_get_crawl_delay(self):
        robots_txt = """
User-agent: *
Crawl-delay: 2
        """
        assert get_crawl_delay(robots_txt, "*") == 2
        assert get_crawl_delay(robots_txt, "test-bot") == 2
        assert get_crawl_delay("", "*") is None

