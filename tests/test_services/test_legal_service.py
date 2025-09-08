"""Tests for the Rechtspraak legal service."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.legal_service import (
    LegalService,
    _extract_kvk_numbers,
)


FIXTURES = Path("tests/fixtures/legal")


@pytest.fixture
def service() -> LegalService:
    return LegalService(rate_limit=1000)  # effectively disable waits in tests


@pytest.fixture
def sample_doc(service: LegalService):
    xml = (FIXTURES / "ecli_content.xml").read_text(encoding="utf-8")
    return service._parse_ecli_content(xml)


# ---------------------------------------------------------------------------
# Parser and KvK extraction
# ---------------------------------------------------------------------------


def test_parse_ecli_content(sample_doc):
    assert sample_doc["ecli"] == "ECLI:NL:TEST:2024:1"
    assert sample_doc["title"].startswith("Testbedrijf")
    assert sample_doc["instantie"]["name"] == "Rechtbank Teststad"
    assert sample_doc["rechtsgebieden"][0]["label"] == "Civiel recht"
    assert sample_doc["zaaknummers"] == ["1234/2024"]
    assert "<p>" not in sample_doc["inhoudsindicatie_text"]
    assert sample_doc["kvk_numbers"] == ["12345678"]


def test_extract_kvk_numbers():
    text = "KvK: 12345678 en ook kamer van koophandel 87654321."  # two numbers
    assert sorted(_extract_kvk_numbers(text)) == ["12345678", "87654321"]
    assert _extract_kvk_numbers("geen nummers") == []


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_noop(service: LegalService):
    """``initialize`` exists for backwards compatibility and does nothing."""
    assert await service.initialize() is None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_by_company(service: LegalService, sample_doc):
    service.index.upsert(sample_doc)
    # Add a second unrelated document
    service.index.upsert(
        {
            "ecli": "ECLI:NL:TEST:2024:2",
            "title": "Andere partij",
            "date": datetime(2024, 1, 20),
            "instantie": {"name": "Rechtbank X", "id": "inst2"},
            "rechtsgebieden": [],
            "zaaknummers": [],
            "kvk_numbers": [],
            "inhoudsindicatie_text": "",
            "full_text": "",
            "deeplink": "http://deeplink.rechtspraak.nl/uitspraak?id=ECLI:NL:TEST:2024:2",
        }
    )

    res = service.search_by_company("Testbedrijf")
    assert len(res) == 1
    assert res[0].ecli == "ECLI:NL:TEST:2024:1"

    # fuzzy search (missing character)
    res = service.search_by_company("Testbedrij")
    assert res and res[0].ecli == "ECLI:NL:TEST:2024:1"

    # date filter excluding the document
    res = service.search_by_company("Testbedrijf", date_from=datetime(2025, 1, 1))
    assert res == []


def test_search_by_kvk(service: LegalService, sample_doc):
    service.index.upsert(sample_doc)
    res = service.search_by_kvk("12345678")
    assert len(res) == 1
    assert res[0].title.startswith("Testbedrijf")


# ---------------------------------------------------------------------------
# Harvester
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_harvest_pagination_and_delete(service: LegalService, sample_doc):
    feed1 = (FIXTURES / "feed_page1.xml").read_text(encoding="utf-8")
    feed2 = (FIXTURES / "feed_page2_deleted.xml").read_text(encoding="utf-8")
    feed3 = (FIXTURES / "feed_empty.xml").read_text(encoding="utf-8")

    # Sequence of responses for search requests
    search_responses = [
        httpx.Response(200, text=feed1),
        httpx.Response(200, text=feed2),
        httpx.Response(200, text=feed3),
    ]

    with patch.object(
        service, "_http_get", new_callable=AsyncMock, side_effect=search_responses
    ):
        service.fetch_ecli_content = AsyncMock(return_value=sample_doc)
        result = await service.harvest(modified="2024-02-01", max=1)

    assert result == {"upserts": 1, "deletes": 1, "pages": 2}
    assert sample_doc["ecli"] in service.index.docs
    assert "ECLI:NL:TEST:2" not in service.index.docs

