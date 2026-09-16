"""The run endpoint, end to end against a real project.

The provider is faked — these tests are about the HTTP layer, persistence and
authorisation, not about what a model says. Nothing here spends credit.

Run with: pytest -m integration
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agenlate.config import Settings
from agenlate.llm import FakeLLM
from agenlate.main import create_app
from agenlate.repository import users

pytestmark = pytest.mark.integration

AGENT = {
    "name": "Researcher",
    "role": "finds information",
    "system_prompt": "You research carefully.",
}
ROOM = {"name": "Blog post", "objective": "Write about coffee trends"}

# Well-formed but not real. The endpoint checks a key's shape before starting a
# run, so a short placeholder is now refused before the provider is reached.
TEST_KEY = "sk-or-v1-" + "0123456789abcdef" * 3


def dispatch(agent_id: str) -> str:
    return json.dumps(
        {
            "reasoning": "Research is needed first.",
            "action": "dispatch",
            "objective_status": "in_progress",
            "agent_id": agent_id,
            "instruction": "Find three sources",
        }
    )


FINISH = json.dumps(
    {
        "reasoning": "The objective is met.",
        "action": "complete",
        "objective_status": "achieved",
        "message_to_user": "Here is your post.",
    }
)


@pytest_asyncio.fixture
async def api(settings: Settings):
    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=60
    ) as client:
        yield client


def auth(user) -> dict:
    return {"Authorization": f"Bearer {user.access_token}"}


@pytest_asyncio.fixture
async def alice_ready(alice_db, alice):
    await users.ensure_user(alice_db, alice.id, alice.email)
    return alice


@pytest_asyncio.fixture
async def bob_ready(bob_db, bob):
    await users.ensure_user(bob_db, bob.id, bob.email)
    return bob


@pytest_asyncio.fixture
async def room(api, alice_ready):
    agent = (await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))).json()
    created = await api.post(
        "/api/rooms", json={**ROOM, "agent_ids": [agent["id"]]}, headers=auth(alice_ready)
    )
    return created.json()


def use_fake_provider(monkeypatch, script: list[str]) -> FakeLLM:
    """Swap the provider without touching anything else in the request path."""
    fake = FakeLLM(script)
    monkeypatch.setattr("agenlate.api.runs.OpenRouterClient", lambda *a, **k: fake)
    return fake


def frames(body: str) -> list[tuple[str, dict]]:
    out = []
    for chunk in body.split("\n\n"):
        lines = [line for line in chunk.split("\n") if line.strip()]
        if len(lines) >= 2 and lines[0].startswith("event: "):
            out.append(
                (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
            )
    return out


class TestAuthorisation:
    async def test_an_anonymous_caller_is_refused(self, api, room) -> None:
        response = await api.post(
            f"/api/rooms/{room['id']}/run", json={"api_key": TEST_KEY}
        )

        assert response.status_code == 401

    async def test_another_users_room_is_not_found(
        self, api, room, bob_ready, monkeypatch
    ) -> None:
        """Answers 404 rather than 403: confirming the room exists would leak
        that it exists."""
        use_fake_provider(monkeypatch, [FINISH])

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(bob_ready),
        )

        assert response.status_code == 404

    async def test_a_missing_key_is_refused(self, api, room, alice_ready) -> None:
        response = await api.post(
            f"/api/rooms/{room['id']}/run", json={}, headers=auth(alice_ready)
        )

        assert response.status_code == 422


class TestStreamingARun:
    async def test_a_complete_run_streams_and_finishes(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        agent_id = room["agents"][0]["id"]
        use_fake_provider(monkeypatch, [dispatch(agent_id), "Found three sources.", FINISH])

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        kinds = [kind for kind, _ in frames(response.text)]
        assert kinds == [
            "usage",
            "supervisor_decision",
            "agent_started",
            "usage",
            "agent_message",
            "usage",
            "supervisor_decision",
            "run_finished",
        ]

    async def test_the_final_frame_reports_the_outcome(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        agent_id = room["agents"][0]["id"]
        use_fake_provider(monkeypatch, [dispatch(agent_id), "Found it.", FINISH])

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        _, finished = frames(response.text)[-1]
        assert finished["reason"] == "completed"
        assert finished["succeeded"] is True
        assert finished["final_message"] == "Here is your post."

    async def test_supervisor_reasoning_reaches_the_client(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        agent_id = room["agents"][0]["id"]
        use_fake_provider(monkeypatch, [dispatch(agent_id), "Found it.", FINISH])

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        decisions = [p for kind, p in frames(response.text) if kind == "supervisor_decision"]
        assert decisions[0]["reasoning"] == "Research is needed first."
        assert decisions[0]["instruction"] == "Find three sources"

    async def test_proxy_buffering_is_disabled(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        """Buffering would hold every event until the run ended, which defeats
        the entire point of streaming it."""
        use_fake_provider(monkeypatch, [FINISH])

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        assert response.headers["x-accel-buffering"] == "no"
        assert "no-cache" in response.headers["cache-control"]


class TestPersistence:
    async def test_the_transcript_survives_the_run(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        agent_id = room["agents"][0]["id"]
        use_fake_provider(monkeypatch, [dispatch(agent_id), "Found three sources.", FINISH])

        await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        page = (
            await api.get(f"/api/rooms/{room['id']}/messages", headers=auth(alice_ready))
        ).json()

        contents = [m["content"] for m in page["items"]]
        assert "Found three sources." in contents
        assert len(contents) == 3

    async def test_a_second_run_continues_the_same_transcript(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        """A room is not reset by running it again; the Supervisor sees what
        already happened."""
        use_fake_provider(monkeypatch, [FINISH])
        await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        fake = use_fake_provider(monkeypatch, [FINISH])
        await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY},
            headers=auth(alice_ready),
        )

        assert "The objective is met." in fake.calls[0]["messages"][0]["content"]


class TestLimits:
    async def test_the_caller_may_lower_the_turn_limit(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        agent_id = room["agents"][0]["id"]
        use_fake_provider(monkeypatch, [dispatch(agent_id), "did it"] * 10)

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY, "max_turns": 1},
            headers=auth(alice_ready),
        )

        _, finished = frames(response.text)[-1]
        assert finished["reason"] == "max_turns"
        assert finished["turns"] == 1

    async def test_an_absurd_spend_cap_is_refused(self, api, room, alice_ready) -> None:
        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": TEST_KEY, "spend_cap_usd": 5000},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422


class TestKeyHandling:
    async def test_the_key_never_appears_in_the_stream(
        self, api, room, alice_ready, monkeypatch
    ) -> None:
        use_fake_provider(monkeypatch, [FINISH])
        key = "sk-or-v1-averydistinctivetestkey000000"

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": key},
            headers=auth(alice_ready),
        )

        assert key not in response.text

    async def test_a_validation_error_does_not_echo_the_key(
        self, api, room, alice_ready
    ) -> None:
        """Validation errors quote the offending input by default, which would
        put the key straight into an error response."""
        key = "sk-or-v1-averydistinctivetestkey000000"

        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": key, "max_turns": 9999},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422
        assert key not in response.text


class TestKeyValidationEndpoint:
    """Checking a key at the point it is entered, rather than three turns into
    a run the user has already set up."""

    async def test_a_real_key_is_confirmed(self, api, alice_ready) -> None:
        import io

        env = {}
        for line in io.open(".env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        key = env.get("OPENROUTER_API_KEY")
        if not key:
            pytest.skip("needs OPENROUTER_API_KEY in backend/.env")

        response = await api.post(
            "/api/keys/validate", json={"api_key": key}, headers=auth(alice_ready)
        )

        assert response.status_code == 200
        assert response.json()["valid"] is True

    async def test_a_well_formed_but_wrong_key_is_rejected_kindly(
        self, api, alice_ready
    ) -> None:
        """Right shape, not a real key: OpenRouter is asked rather than
        guessed at."""
        fake = "sk-or-v1-" + "0" * 48

        response = await api.post(
            "/api/keys/validate", json={"api_key": fake}, headers=auth(alice_ready)
        )

        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert "key" in response.json()["message"].lower()

    async def test_a_malformed_key_never_reaches_openrouter(
        self, api, alice_ready
    ) -> None:
        response = await api.post(
            "/api/keys/validate", json={"api_key": "clearly-not-a-key"},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422

    async def test_validation_never_echoes_the_key(self, api, alice_ready) -> None:
        key = "sk-distinctive-wrong-shaped-value-000000"

        response = await api.post(
            "/api/keys/validate", json={"api_key": key}, headers=auth(alice_ready)
        )

        assert response.status_code == 422
        assert key not in response.text

    async def test_the_endpoint_requires_a_signed_in_caller(self, api) -> None:
        response = await api.post(
            "/api/keys/validate", json={"api_key": "sk-or-v1-" + "0" * 48}
        )

        assert response.status_code == 401

    async def test_a_malformed_key_is_refused_by_the_run_endpoint_too(
        self, api, room, alice_ready
    ) -> None:
        """Validating at entry is a convenience; the run endpoint still has to
        refuse, because nothing stops a client skipping the check."""
        response = await api.post(
            f"/api/rooms/{room['id']}/run",
            json={"api_key": "nonsense"},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422
