import pytest

from app.services import google_search
from app.services.google_search import GoogleSearchClient


def test_is_probable_news_url():
    assert GoogleSearchClient._is_probable_news_url(
        "https://nos.nl/2024/05/05/nieuws/test.html"
    )
    assert not GoogleSearchClient._is_probable_news_url(
        "https://example.com/about"
    )


@pytest.mark.asyncio
async def test_search_filters_news_urls(monkeypatch):
    sample_data = {
        "items": [
            {"link": "https://example.com/about", "title": "About"},
            {
                "link": "https://nos.nl/2024/05/05/nieuws/test.html",
                "title": "Nieuws",
            },
        ]
    }

    class DummyResponse:
        status_code = 200

        def json(self):
            return sample_data

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, *args, **kwargs):
            return DummyResponse()

    monkeypatch.setattr(google_search.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(google_search.settings, "GOOGLE_SEARCH_API_KEY", "k")
    monkeypatch.setattr(google_search.settings, "GOOGLE_SEARCH_ENGINE_ID", "cx")
    monkeypatch.setattr(google_search.settings, "EXTERNAL_SERVICE_TIMEOUT", 5)

    client = GoogleSearchClient()
    results = await client.search("test", news_only=True)

    assert len(results) == 1
    assert results[0]["url"] == "https://nos.nl/2024/05/05/nieuws/test.html"
