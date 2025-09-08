import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from app.services.legal_service import LegalService
from app.api.endpoints.analyze import _fetch_legal_findings_by_name
from app.models.response_models import LegalCase
from app.utils.text_utils import (
    normalize_company_name,
    calculate_similarity,
    match_company_variations,
)
from app.utils.web_utils import is_path_allowed, get_crawl_delay


@pytest.fixture
def legal_service():
    with patch("app.services.legal_service.settings") as mock_settings:
        mock_settings.APP_NAME = "test-app"
        mock_settings.RECHTSPRAAK_TIMEOUT = 30
        return LegalService()


@pytest.mark.asyncio
async def test_parse_atom_index_multiple_entries(legal_service):
    atom_xml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry><id>ECLI:1</id><title>ECLI:1, Court A, 2024-01-01, Title A</title></entry>"
        "<entry><id>ECLI:2</id><title>ECLI:2, Court B, 2024-01-02, Title B</title></entry>"
        "</feed>"
    )
    results = legal_service._parse_atom_index(atom_xml)
    assert len(results) == 2
    assert results[0]["ecli"] == "ECLI:1"


def test_party_matcher_variants(legal_service):
    text = "De ING Bank N.V. had een geschil. Ook wordt de ING Groep genoemd."
    assert legal_service._match_party_name(text, "ING Bank N.V.")
    assert not legal_service._match_party_name("Geen relevante partijen hier.", "ING Bank N.V.")


@pytest.mark.asyncio
async def test_search_company_cases_integration(legal_service):
    atom_xml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry><id>ECLI:NL:TEST:2024:1</id><title>ECLI:NL:TEST:2024:1, Court A, 2024-01-01, Title A</title></entry>"
        "<entry><id>ECLI:NL:TEST:2024:2</id><title>ECLI:NL:TEST:2024:2, Court B, 2024-01-02, Title B</title></entry>"
        "<entry><id>ECLI:NL:TEST:2024:3</id><title>ECLI:NL:TEST:2024:3, Court C, 2024-01-03, Title C</title></entry>"
        "</feed>"
    )

    details = {
        "ECLI:NL:TEST:2024:1": {"summary": "Geschil met ING Bank", "full_text": "", "case_number": "1", "parties": []},
        "ECLI:NL:TEST:2024:2": {"summary": "Andere partij", "full_text": "", "case_number": "2", "parties": []},
        "ECLI:NL:TEST:2024:3": {"summary": "Nog een zaak", "full_text": "", "case_number": "3", "parties": []},
    }

    with patch.object(LegalService, "_fetch_api_search", new=AsyncMock(return_value=atom_xml)):
        with patch.object(
            LegalService,
            "_fetch_case_details",
            new=AsyncMock(side_effect=lambda ecli: details[ecli]),
        ):
            cases = await legal_service.search_company_cases("ING Bank N.V.")

    assert len(cases) == 1
    assert cases[0].ecli == "ECLI:NL:TEST:2024:1"
    assert legal_service.last_results_count == 3
    assert legal_service.last_match_count == 1


@pytest.mark.asyncio
async def test_no_match_sets_unknown_risk(legal_service):
    atom_xml = (
        "<?xml version='1.0' encoding='utf-8'?><feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry><id>ECLI:NL:TEST:2024:10</id><title>ECLI:NL:TEST:2024:10, Court A, 2024-01-01, Title A</title></entry>"
        "</feed>"
    )
    details = {"ECLI:NL:TEST:2024:10": {"summary": "Geen partij genoemd", "full_text": "", "case_number": "10", "parties": []}}

    with patch.object(LegalService, "_fetch_api_search", new=AsyncMock(return_value=atom_xml)):
        with patch.object(LegalService, "_fetch_case_details", new=AsyncMock(side_effect=lambda ecli: details[ecli])):
            cases = await legal_service.search_company_cases("ING Bank N.V.")

    assert cases == []
    lf = await _fetch_legal_findings_by_name(legal_service, "ING Bank N.V.")
    assert lf.risk_level == "unknown"


def test_deduplicate_cases(legal_service):
    cases = [
        {"url": "https://example.com/1", "ecli": "ECLI:NL:TEST:1"},
        {"url": "https://example.com/1", "ecli": "ECLI:NL:TEST:1"},
        {"url": "https://example.com/2", "ecli": "ECLI:NL:TEST:2"},
    ]
    unique = legal_service._deduplicate_cases(cases)
    assert len(unique) == 2


def test_assess_legal_risk_high(legal_service):
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
