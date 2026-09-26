"""Whether the interactive API docs are published.

Every endpoint needs a token, so the docs leak no data. They are still a
browsable map of the whole API with a button on every route, and in production
there is nobody outside this repository they are for.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.config import Settings
from agenlate.main import create_app

DOC_ROUTES = ["/docs", "/redoc", "/openapi.json"]


def _settings(env: str) -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        api_env=env,
        api_cors_origins="https://agenlate.example",
    )


async def _status(env: str, path: str) -> int:
    # Built per test rather than taken from the shared fixture: whether the
    # routes exist is decided when the app is created, so changing the
    # environment on an existing app would test nothing.
    app = create_app(_settings(env))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return (await c.get(path)).status_code


@pytest.mark.parametrize("path", DOC_ROUTES)
async def test_production_does_not_publish_them(path: str) -> None:
    assert await _status("production", path) == 404


@pytest.mark.parametrize("path", DOC_ROUTES)
async def test_development_still_does(path: str) -> None:
    assert await _status("development", path) == 200


def test_the_schema_still_builds_in_production() -> None:
    """The frontend's types are generated from `app.openapi()`, not from the
    route. Turning the route off must not take the schema with it."""
    schema = create_app(_settings("production")).openapi()

    assert "/api/rooms" in schema["paths"]
