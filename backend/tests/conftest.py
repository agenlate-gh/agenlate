"""Shared test fixtures.

Settings are constructed explicitly rather than read from the environment, so
the suite runs identically on a laptop with a populated .env and on CI with
nothing set. No test requires an API key or network access.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.config import Settings
from agenlate.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        api_env="development",
        api_cors_origins="http://localhost:3000",
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
