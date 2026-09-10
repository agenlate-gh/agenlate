"""The health endpoint. Also the target of the production keep-alive ping."""

from __future__ import annotations

from httpx import AsyncClient

from agenlate import __version__


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "environment": "development",
    }


async def test_health_reports_configured_environment(settings, client: AsyncClient) -> None:
    settings.api_env = "production"
    response = await client.get("/health")

    assert response.json()["environment"] == "production"
