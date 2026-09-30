"""Shared test fixtures.

Settings are constructed explicitly rather than read from the environment, so
the suite runs identically on a laptop with a populated .env and on CI with
nothing set. No test requires an API key or network access.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.api.limits import reset_anonymous_limiters
from agenlate.config import Settings
from agenlate.main import create_app


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Every test starts with empty per-address limits.

    They are process-wide, and every test client shares one address — so
    without this, the tests' own requests would add up across the suite and
    start tripping the limits they are not about.
    """
    reset_anonymous_limiters()
    yield
    reset_anonymous_limiters()


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
