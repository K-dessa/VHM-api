from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_status_endpoint(client):
    """Test the simple status endpoint."""
    response = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_endpoint_all_healthy(client):
    """Test health endpoint when all services are healthy."""
    with patch("app.api.endpoints.health.check_kvk_api", return_value="healthy"), patch(
        "app.api.endpoints.health.check_openai_api", return_value="healthy"
    ), patch("app.api.endpoints.health.check_rechtspraak_nl", return_value="healthy"):
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["dependencies"]["kvk_api"] == "healthy"
        assert data["dependencies"]["openai_api"] == "healthy"
        assert data["dependencies"]["rechtspraak_nl"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
        assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_health_endpoint_degraded(client):
    """Test health endpoint when some services are degraded."""
    with patch("app.api.endpoints.health.check_kvk_api", return_value="healthy"), patch(
        "app.api.endpoints.health.check_openai_api", return_value="degraded"
    ), patch("app.api.endpoints.health.check_rechtspraak_nl", return_value="healthy"):
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["openai_api"] == "degraded"


@pytest.mark.asyncio
async def test_health_endpoint_unhealthy(client):
    """Test health endpoint when some services are unhealthy."""
    with patch(
        "app.api.endpoints.health.check_kvk_api", return_value="unhealthy"
    ), patch(
        "app.api.endpoints.health.check_openai_api", return_value="healthy"
    ), patch(
        "app.api.endpoints.health.check_rechtspraak_nl", return_value="healthy"
    ):
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["dependencies"]["kvk_api"] == "unhealthy"


@pytest.mark.asyncio
async def test_check_kvk_api_no_key():
    """Test KvK API check when no API key is configured."""
    from app.api.endpoints.health import check_kvk_api

    with patch("app.core.config.settings.KVK_API_KEY", None):
        status = await check_kvk_api()
        assert status == "unavailable"


@pytest.mark.asyncio
async def test_check_kvk_api_success():
    """Test successful KvK API check."""
    from app.api.endpoints.health import check_kvk_api

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )
        with patch("app.core.config.settings.KVK_API_KEY", "test-key"):
            status = await check_kvk_api()
            assert status == "healthy"


@pytest.mark.asyncio
async def test_check_kvk_api_unauthorized():
    """Test KvK API check with invalid API key."""
    from app.api.endpoints.health import check_kvk_api

    mock_response = AsyncMock()
    mock_response.status_code = 401

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )
        with patch("app.core.config.settings.KVK_API_KEY", "invalid-key"):
            status = await check_kvk_api()
            assert status == "unhealthy"


@pytest.mark.asyncio
async def test_check_openai_api_no_key():
    """Test OpenAI API check when no API key is configured."""
    from app.api.endpoints.health import check_openai_api

    with patch("app.core.config.settings.OPENAI_API_KEY", None):
        status = await check_openai_api()
        assert status == "unavailable"


@pytest.mark.asyncio
async def test_check_rechtspraak_nl_success():
    """Test successful rechtspraak.nl check."""
    from app.api.endpoints.health import check_rechtspraak_nl

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )
        status = await check_rechtspraak_nl()
        assert status == "healthy"


@pytest.mark.asyncio
async def test_health_check_exception_handling():
    """Test health check handles exceptions properly."""
    from app.api.endpoints.health import check_kvk_api

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = Exception("Connection error")
        with patch("app.core.config.settings.KVK_API_KEY", "test-key"):
            status = await check_kvk_api()
            assert status == "unhealthy"
