"""The public waitlist, and the per-address limits on public endpoints.

Anyone on the internet can reach these, so what matters is what they refuse
to reveal and how they hold up against a script, as much as whether they work.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.api import waitlist as waitlist_api
from agenlate.api.limits import WindowLimiter, client_address
from agenlate.main import create_app


class FakeWaitlist:
    def __init__(self) -> None:
        self.emails: dict[str, str] = {}

    async def join(self, _client, email: str, source: str) -> None:
        self.emails.setdefault(email, source)


@pytest.fixture
def stored(monkeypatch):
    table = FakeWaitlist()

    async def fake_service_client(_settings):
        async def aclose() -> None:
            return None

        return SimpleNamespace(postgrest=SimpleNamespace(aclose=aclose))

    monkeypatch.setattr(waitlist_api, "create_service_client", fake_service_client)
    monkeypatch.setattr(waitlist_api.waitlist_repo, "join", table.join)
    return table


@pytest.fixture
async def api(settings):
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestJoining:
    async def test_an_email_is_stored(self, api, stored) -> None:
        response = await api.post("/api/waitlist", json={"email": "Ada@Example.com"})

        assert response.status_code == 202
        # Lowercased, so the same person typed two ways is one entry.
        assert "ada@example.com" in stored.emails

    async def test_no_login_is_needed(self, api, stored) -> None:
        response = await api.post("/api/waitlist", json={"email": "a@example.com"})

        assert response.status_code != 401

    async def test_joining_twice_looks_the_same_as_joining_once(self, api, stored) -> None:
        """A different answer for an address already on the list would let
        anyone check who has signed up."""
        first = await api.post("/api/waitlist", json={"email": "a@example.com"})
        second = await api.post("/api/waitlist", json={"email": "a@example.com"})

        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()

    async def test_the_source_is_recorded_as_a_tidy_label(self, api, stored) -> None:
        await api.post("/api/waitlist", json={"email": "a@example.com", "source": " Casa212! "})

        assert stored.emails["a@example.com"] == "casa212"

    async def test_an_obviously_wrong_email_is_refused(self, api, stored) -> None:
        response = await api.post("/api/waitlist", json={"email": "not-an-email"})

        assert response.status_code == 422
        assert stored.emails == {}


class TestBots:
    async def test_a_filled_trap_field_is_dropped_silently(self, api, stored) -> None:
        """Answered exactly as a person would be, so the bot learns nothing,
        but nothing is stored."""
        person = await api.post("/api/waitlist", json={"email": "p@example.com"})
        bot = await api.post(
            "/api/waitlist", json={"email": "b@example.com", "website": "http://spam"}
        )

        assert bot.status_code == person.status_code
        assert bot.json() == person.json()
        assert "b@example.com" not in stored.emails

    async def test_a_script_in_a_loop_is_stopped(self, api, stored) -> None:
        codes = [
            (await api.post("/api/waitlist", json={"email": f"u{i}@example.com"})).status_code
            for i in range(waitlist_api.JOINS_PER_ADDRESS + 2)
        ]

        assert codes[: waitlist_api.JOINS_PER_ADDRESS] == [202] * waitlist_api.JOINS_PER_ADDRESS
        assert codes[-1] == 429

    async def test_the_limit_is_per_address(self, api, stored) -> None:
        for i in range(waitlist_api.JOINS_PER_ADDRESS):
            await api.post(
                "/api/waitlist",
                json={"email": f"a{i}@example.com"},
                headers={"x-forwarded-for": "203.0.113.1"},
            )

        other = await api.post(
            "/api/waitlist",
            json={"email": "b@example.com"},
            headers={"x-forwarded-for": "203.0.113.2"},
        )

        assert other.status_code == 202


class TestWindowLimiter:
    def test_it_allows_up_to_the_limit_then_refuses(self) -> None:
        limiter = WindowLimiter(limit=2, window_seconds=60)

        assert [limiter.allow("k") for _ in range(3)] == [True, True, False]

    def test_keys_are_independent(self) -> None:
        limiter = WindowLimiter(limit=1, window_seconds=60)

        assert limiter.allow("a") and limiter.allow("b")

    def test_the_window_slides(self, monkeypatch) -> None:
        clock = [1000.0]
        monkeypatch.setattr("agenlate.api.limits.time.monotonic", lambda: clock[0])
        limiter = WindowLimiter(limit=1, window_seconds=60)

        assert limiter.allow("k") is True
        assert limiter.allow("k") is False
        clock[0] += 60
        assert limiter.allow("k") is True


class TestClientAddress:
    def test_the_first_forwarded_address_is_the_client(self) -> None:
        request = SimpleNamespace(
            headers={"x-forwarded-for": "198.51.100.7, 10.0.0.1"},
            client=SimpleNamespace(host="10.0.0.1"),
        )

        assert client_address(request) == "198.51.100.7"

    def test_without_a_proxy_header_the_peer_is_used(self) -> None:
        request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))

        assert client_address(request) == "127.0.0.1"
