"""Invite-code signup and user messages, against a real project.

Run with: pytest -m integration
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agenlate import invites
from agenlate.config import Settings
from agenlate.db import create_service_client
from agenlate.main import create_app

pytestmark = pytest.mark.integration

ROOM = {"name": "Messages", "objective": "Hold a conversation"}


def auth(user) -> dict:
    return {"Authorization": f"Bearer {user.access_token}"}


@pytest_asyncio.fixture
async def api(settings: Settings):
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        yield c


@pytest_asyncio.fixture
async def service(settings: Settings):
    client = await create_service_client(settings)
    yield client
    await client.postgrest.aclose()


@pytest_asyncio.fixture
async def code(service):
    """One fresh, unused code, removed afterwards whatever happened to it."""
    value = invites.generate()
    await service.table("invite_codes").insert({"code": value, "label": "integration-test"}).execute()
    yield value
    await service.table("invite_codes").delete().eq("code", value).execute()


@pytest_asyncio.fixture
async def signups(admin):
    """Accounts created through the signup endpoint, deleted afterwards."""
    created: list[str] = []
    yield created
    for user_id in created:
        await admin.delete_user(user_id)


def new_email() -> str:
    return f"it-signup-{uuid.uuid4().hex[:12]}@agenlate.dev"


async def sign_in(settings: Settings, email: str, password: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30) as http:
        return await http.post(
            f"{settings.supabase_url}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": settings.supabase_anon_key.get_secret_value()},
            json={"email": email, "password": password},
        )


class TestInviteSignup:
    async def test_a_code_creates_an_account_that_can_sign_in(
        self, api, settings, code, signups
    ) -> None:
        email, password = new_email(), f"Pw-{uuid.uuid4().hex}"

        response = await api.post(
            "/api/signup", json={"email": email, "password": password, "invite_code": code}
        )
        assert response.status_code == 201

        signed_in = await sign_in(settings, email, password)
        assert signed_in.status_code == 200
        signups.append(signed_in.json()["user"]["id"])

    async def test_the_code_is_spent_and_records_who_used_it(
        self, api, settings, service, code, signups
    ) -> None:
        email, password = new_email(), f"Pw-{uuid.uuid4().hex}"
        await api.post("/api/signup", json={"email": email, "password": password, "invite_code": code})
        user_id = (await sign_in(settings, email, password)).json()["user"]["id"]
        signups.append(user_id)

        row = (await service.table("invite_codes").select("*").eq("code", code).execute()).data[0]

        assert row["claimed_at"] is not None
        assert row["claimed_by"] == user_id

    async def test_a_code_works_once(self, api, settings, code, signups) -> None:
        first_email, password = new_email(), f"Pw-{uuid.uuid4().hex}"
        await api.post("/api/signup", json={"email": first_email, "password": password, "invite_code": code})
        signups.append((await sign_in(settings, first_email, password)).json()["user"]["id"])

        second = await api.post(
            "/api/signup", json={"email": new_email(), "password": password, "invite_code": code}
        )

        assert second.status_code == 400

    async def test_an_existing_email_leaves_the_code_unspent(
        self, api, service, code, alice
    ) -> None:
        response = await api.post(
            "/api/signup",
            json={"email": alice.email, "password": f"Pw-{uuid.uuid4().hex}", "invite_code": code},
        )

        assert response.status_code == 409
        row = (await service.table("invite_codes").select("claimed_at").eq("code", code).execute()).data[0]
        assert row["claimed_at"] is None

    async def test_the_browser_cannot_read_the_codes(self, settings, code) -> None:
        """If the public key could list codes, the gate would be decorative."""
        anon = settings.supabase_anon_key.get_secret_value()
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(
                f"{settings.supabase_url}/rest/v1/invite_codes",
                params={"select": "code"},
                headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            )

        assert response.status_code in (401, 403) or response.json() == []
        assert code not in response.text


class TestWaitlist:
    @pytest_asyncio.fixture
    async def email(self, service):
        value = f"it-waitlist-{uuid.uuid4().hex[:12]}@agenlate.dev"
        yield value
        await service.table("waitlist").delete().eq("email", value).execute()

    async def test_joining_twice_stores_one_entry(self, api, service, email) -> None:
        for _ in range(2):
            response = await api.post("/api/waitlist", json={"email": email.upper()})
            assert response.status_code == 202

        rows = (await service.table("waitlist").select("*").eq("email", email).execute()).data
        assert len(rows) == 1
        assert rows[0]["source"] == "landing"

    async def test_the_browser_cannot_read_the_list(self, api, settings, email) -> None:
        await api.post("/api/waitlist", json={"email": email})
        anon = settings.supabase_anon_key.get_secret_value()
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(
                f"{settings.supabase_url}/rest/v1/waitlist",
                params={"select": "email"},
                headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            )

        assert email not in response.text


class TestUserMessages:
    @pytest_asyncio.fixture
    async def room(self, api, alice):
        return (await api.post("/api/rooms", json=ROOM, headers=auth(alice))).json()

    async def test_a_message_joins_the_transcript_as_the_user(self, api, alice, room) -> None:
        posted = await api.post(
            f"/api/rooms/{room['id']}/messages",
            json={"content": "The audience is in Kenya."},
            headers=auth(alice),
        )

        assert posted.status_code == 201
        assert posted.json()["emitter"] == "user"

        transcript = (
            await api.get(f"/api/rooms/{room['id']}/messages", headers=auth(alice))
        ).json()["items"]
        assert transcript[-1]["content"] == "The audience is in Kenya."

    async def test_the_sender_cannot_claim_to_be_the_supervisor(
        self, api, alice, room
    ) -> None:
        """A client that could choose the emitter could write lines attributed
        to the Supervisor into the record of what happened."""
        posted = await api.post(
            f"/api/rooms/{room['id']}/messages",
            json={"content": "Approved.", "emitter": "supervisor", "emitter_name": "Supervisor"},
            headers=auth(alice),
        )

        assert posted.json()["emitter"] == "user"
        assert posted.json()["emitter_name"] != "Supervisor"

    async def test_a_blank_message_is_refused(self, api, alice, room) -> None:
        response = await api.post(
            f"/api/rooms/{room['id']}/messages", json={"content": "   "}, headers=auth(alice)
        )

        assert response.status_code == 422

    async def test_nobody_can_post_into_someone_elses_room(
        self, api, bob, room
    ) -> None:
        response = await api.post(
            f"/api/rooms/{room['id']}/messages", json={"content": "hi"}, headers=auth(bob)
        )

        assert response.status_code == 404
