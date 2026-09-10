"""Fixtures for tests that talk to a real Supabase project.

Users are created through the admin API rather than signup. Signup sends a
confirmation email, and Supabase's built-in mailer is rate limited to a couple
of sends an hour, which makes a signup-based suite unrunnable. Admin creation
with email_confirm skips the mail path entirely.

Every client here carries a real user JWT, so these tests exercise the same
row-level security path that production does. Nothing uses the service role to
read or write application data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from supabase import AsyncClient

from agenlate.config import Settings
from agenlate.db import create_user_client

def _settings() -> Settings:
    """Load settings the same way the application does.

    Reading os.environ directly would miss backend/.env, which is where these
    values actually live during development.
    """
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        pytest.skip(f"integration tests need credentials in backend/.env: {exc}")
    if not settings.supabase_service_role_key.get_secret_value():
        pytest.skip("integration tests need SUPABASE_SERVICE_ROLE_KEY in backend/.env")
    return settings


@dataclass
class TestUser:
    id: str
    email: str
    access_token: str


class _Admin:
    """Thin wrapper over the Supabase auth admin API."""

    def __init__(self, url: str, service_key: str, anon_key: str) -> None:
        self._url = url.rstrip("/")
        self._service_key = service_key
        self._anon_key = anon_key

    async def create_user(self) -> TestUser:
        email = f"it-{uuid.uuid4().hex[:12]}@agenlate.dev"
        password = f"It-{uuid.uuid4().hex}!"

        async with httpx.AsyncClient(timeout=30) as http:
            created = await http.post(
                f"{self._url}/auth/v1/admin/users",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                },
                json={"email": email, "password": password, "email_confirm": True},
            )
            created.raise_for_status()
            user_id = created.json()["id"]

            token = await http.post(
                f"{self._url}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": self._anon_key},
                json={"email": email, "password": password},
            )
            token.raise_for_status()
            access_token = token.json()["access_token"]

        return TestUser(id=user_id, email=email, access_token=access_token)

    async def delete_user(self, user_id: str) -> None:
        async with httpx.AsyncClient(timeout=30) as http:
            await http.delete(
                f"{self._url}/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                },
            )


@pytest.fixture(scope="session")
def settings() -> Settings:
    return _settings()


@pytest.fixture(scope="session")
def admin(settings: Settings) -> _Admin:
    return _Admin(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
        settings.supabase_anon_key.get_secret_value(),
    )


@pytest_asyncio.fixture
async def alice(admin: _Admin):
    user = await admin.create_user()
    yield user
    # Deleting the auth user cascades through every application table.
    await admin.delete_user(user.id)


@pytest_asyncio.fixture
async def bob(admin: _Admin):
    user = await admin.create_user()
    yield user
    await admin.delete_user(user.id)


@pytest_asyncio.fixture
async def alice_db(settings: Settings, alice: TestUser) -> AsyncClient:
    client = await create_user_client(settings, alice.access_token)
    yield client
    await client.postgrest.aclose()


@pytest_asyncio.fixture
async def bob_db(settings: Settings, bob: TestUser) -> AsyncClient:
    client = await create_user_client(settings, bob.access_token)
    yield client
    await client.postgrest.aclose()
