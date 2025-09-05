import asyncio
import os
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient

# Set testing environment variable
os.environ["TESTING"] = "true"

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings.KVK_API_KEY = "test-kvk-key"
    settings.OPENAI_API_KEY = "test-openai-key"
    settings.DEBUG = True
    return settings


@pytest.fixture
def mock_kvk_api_response():
    """Mock KvK API response."""
    return {
        "kvkNummer": "27312152",
        "naam": "Test Company B.V.",
        "handelsnaam": "Test Company",
        "rechtsvorm": "Besloten Vennootschap",
        "datumOprichting": "2020-01-01",
        "adres": {
            "straatnaam": "Teststraat",
            "huisnummer": "1",
            "postcode": "1234AB",
            "plaats": "Amsterdam",
        },
        "activiteiten": ["Test Activity 1", "Test Activity 2"],
        "werknemers": "1-9",
        "status": "Actief",
    }


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-4-turbo",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from OpenAI.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for external API calls."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Mock successful responses by default
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response

    return mock_client


@pytest.fixture(autouse=True)
def mock_external_apis(monkeypatch, mock_httpx_client):
    """Automatically mock external API calls in all tests."""
    # Mock httpx.AsyncClient
    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_httpx_client)

    # Mock specific API endpoints if needed
    return mock_httpx_client
