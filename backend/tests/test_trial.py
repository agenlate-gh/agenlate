"""Trial runs: a new account's first few runs, on Agenlate's key.

This is the one path where the money being spent is ours, so most of what is
tested here is what it refuses: more uses than an account gets, more than the
Beta has, a model or a spending cap other than the trial's own.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.api import runs as runs_api
from agenlate.api import trial as trial_api
from agenlate.api.deps import user_db
from agenlate.api.limits import reset_run_limiter
from agenlate.auth import CurrentUser, current_user
from agenlate.config import Settings
from agenlate.llm import FakeLLM, LLMAuthError, LLMCreditError
from agenlate.main import create_app
from agenlate.models import Agent, Room, RoomStatus, RoomWithAgents
from agenlate.repository.trial import Claim
from agenlate.store import InMemoryRunStore

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
USER_KEY = "sk-or-v1-" + "0123456789abcdef" * 3
OUR_KEY = "sk-or-v1-" + "fedcba9876543210" * 3
TRIAL_MODEL = "qwen/qwen3.7-flash"

FINISH = json.dumps(
    {
        "reasoning": "The objective is met.",
        "action": "complete",
        "objective_status": "achieved",
        "message_to_user": "Done.",
    }
)
DRAFT = json.dumps(
    {"reply": "Here it is.", "objective": "Write the post.", "name": "Coffee", "needs_answer": False}
)


class FakeUses:
    """The trial table, with the database function's rules."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.released: list[str] = []

    async def claim(self, _client, *, user_id, kind, room_id, user_limit, total_limit) -> Claim:
        mine = [r for r in self.rows if r["user_id"] == user_id and r["kind"] == kind]
        if len(mine) >= user_limit:
            return Claim(outcome="user_limit")
        if len([r for r in self.rows if r["kind"] == kind]) >= total_limit:
            return Claim(outcome="total_limit")
        use_id = f"use-{len(self.rows) + 1}"
        self.rows.append({"id": use_id, "user_id": user_id, "kind": kind, "room_id": room_id})
        return Claim(outcome="claimed", remaining=user_limit - len(mine) - 1, use_id=use_id)

    async def release(self, _client, use_id: str) -> None:
        self.released.append(use_id)
        self.rows = [r for r in self.rows if r["id"] != use_id]

    async def used(self, _client, user_id: str, kind: str) -> int:
        return len([r for r in self.rows if r["user_id"] == user_id and r["kind"] == kind])

    def count(self, kind: str) -> int:
        return len([r for r in self.rows if r["kind"] == kind])


@pytest.fixture
def uses(monkeypatch) -> FakeUses:
    table = FakeUses()

    async def fake_service_client(_settings):
        async def aclose() -> None:
            return None

        return SimpleNamespace(postgrest=SimpleNamespace(aclose=aclose))

    monkeypatch.setattr(trial_api, "create_service_client", fake_service_client)
    for name in ("claim", "release", "used"):
        monkeypatch.setattr(trial_api.trial_repo, name, getattr(table, name))
    return table


def settings_with(**overrides) -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        api_env="development",
        api_cors_origins="http://localhost:3000",
        **overrides,
    )


def trial_on(**overrides) -> Settings:
    return settings_with(trial_openrouter_key=OUR_KEY, trial_model=TRIAL_MODEL, **overrides)


def make_room() -> RoomWithAgents:
    agent = Agent(
        id="agent-0",
        creator_id="u1",
        name="Writer",
        role="writes",
        system_prompt="You write.",
        created_at=NOW,
        updated_at=NOW,
    )
    room = Room(
        id="r1",
        creator_id="u1",
        name="Post",
        objective="Write a post",
        created_at=NOW,
        updated_at=NOW,
    )
    return RoomWithAgents(room=room, agents=[agent])


class Api:
    """A client for one app, with the provider and the database swapped out."""

    def __init__(self, settings: Settings, monkeypatch, script: list) -> None:
        self.app = create_app(settings)
        self.app.dependency_overrides[current_user] = lambda: CurrentUser(
            id="u1", email="u1@example.com"
        )
        self.app.dependency_overrides[user_db] = lambda: object()
        self.fake = FakeLLM(script)
        self.provider: dict = {}
        self.limits = None

        def provider(key, **kwargs):
            self.provider = {"key": key, **kwargs}
            return self.fake

        for module in ("runs", "objective", "builder"):
            monkeypatch.setattr(f"agenlate.api.{module}.OpenRouterClient", provider)

        async def room(_db, _room_id):
            return make_room()

        async def no_messages(_db, _room_id):
            return []

        real_run_room = runs_api.run_room

        def run_room(*args, **kwargs):
            self.limits = kwargs.get("limits")
            return real_run_room(*args, **kwargs)

        monkeypatch.setattr(runs_api.rooms_repo, "get_room_with_agents", room)
        monkeypatch.setattr(runs_api.messages_repo, "list_messages", no_messages)
        monkeypatch.setattr(runs_api, "SupabaseRunStore", lambda _db: InMemoryRunStore("r1"))
        monkeypatch.setattr(runs_api, "run_room", run_room)

    async def post(self, path: str, body: dict):
        async with AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            return await client.post(path, json=body)

    async def get(self, path: str):
        async with AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            return await client.get(path)

    async def run(self, **body):
        return await self.post("/api/rooms/r1/run", body)

    async def draft(self, **body):
        return await self.post(
            "/api/rooms/objective-draft",
            {"conversation": [{"role": "user", "content": "a coffee post"}], **body},
        )


@pytest.fixture(autouse=True)
def _fresh_run_limits():
    reset_run_limiter()
    yield
    reset_run_limiter()


def finished(response) -> dict:
    """The run_finished frame of a streamed run."""
    for chunk in response.text.split("\n\n"):
        lines = [line for line in chunk.split("\n") if line.strip()]
        if len(lines) >= 2 and lines[0] == "event: run_finished":
            return json.loads(lines[1].removeprefix("data: "))
    raise AssertionError(f"no run_finished frame in: {response.text[:300]}")


class TestSwitchedOff:
    """With no key of ours configured, nothing changes for anyone."""

    async def test_a_run_without_a_key_is_told_to_add_one(self, monkeypatch, uses) -> None:
        api = Api(settings_with(), monkeypatch, [FINISH])

        response = await api.run()

        assert response.status_code == 402
        assert response.json()["error"]["code"] == "key_required"
        assert api.fake.call_count == 0
        assert uses.rows == []

    async def test_a_run_with_the_users_own_key_still_works(self, monkeypatch, uses) -> None:
        api = Api(settings_with(), monkeypatch, [FINISH])

        response = await api.run(api_key=USER_KEY, model="some/model")

        assert response.status_code == 200
        assert api.provider["key"] == USER_KEY
        assert api.provider["model"] == "some/model"

    async def test_the_status_says_there_is_no_trial(self, monkeypatch, uses) -> None:
        api = Api(settings_with(), monkeypatch, [])

        response = await api.get("/api/trial")

        assert response.json() == {
            "enabled": False,
            "runs_total": 0,
            "runs_remaining": 0,
            "model": None,
        }


class TestFreeRuns:
    async def test_a_run_without_a_key_uses_ours(self, monkeypatch, uses) -> None:
        api = Api(trial_on(), monkeypatch, [FINISH])

        response = await api.run()

        assert response.status_code == 200
        assert finished(response)["reason"] == "completed"
        assert api.provider["key"] == OUR_KEY
        assert uses.count("run") == 1
        assert uses.rows[0]["room_id"] == "r1"

    async def test_the_model_is_ours_to_choose(self, monkeypatch, uses) -> None:
        """Otherwise the first thing anyone does with a free run is pick the
        most expensive model on the list."""
        api = Api(trial_on(), monkeypatch, [FINISH])

        await api.run(model="anthropic/claude-sonnet-5")

        assert api.provider["model"] == TRIAL_MODEL

    async def test_the_ceilings_are_ours_whatever_was_asked_for(
        self, monkeypatch, uses
    ) -> None:
        api = Api(
            trial_on(trial_run_spend_cap_usd=0.08, trial_run_max_turns=12),
            monkeypatch,
            [FINISH],
        )

        await api.run(spend_cap_usd=20, max_turns=50)

        assert api.limits.spend_cap_usd == 0.08
        assert api.limits.max_turns == 12

    async def test_a_lower_ceiling_the_user_asked_for_is_kept(self, monkeypatch, uses) -> None:
        api = Api(trial_on(trial_run_max_turns=12), monkeypatch, [FINISH])

        await api.run(max_turns=3)

        assert api.limits.max_turns == 3

    async def test_a_users_own_key_is_never_swapped_for_ours(self, monkeypatch, uses) -> None:
        api = Api(trial_on(), monkeypatch, [FINISH])

        await api.run(api_key=USER_KEY, model="anthropic/claude-sonnet-5")

        assert api.provider["key"] == USER_KEY
        assert api.provider["model"] == "anthropic/claude-sonnet-5"
        assert uses.rows == []

    async def test_a_malformed_key_is_still_refused(self, monkeypatch, uses) -> None:
        """Not treated as "no key": a typo should not quietly spend a free run."""
        api = Api(trial_on(), monkeypatch, [FINISH])

        response = await api.run(api_key="not-a-key")

        assert response.status_code == 422
        assert "not-a-key" not in response.text
        assert uses.rows == []


class TestLimits:
    async def test_an_account_gets_only_so_many(self, monkeypatch, uses) -> None:
        api = Api(trial_on(trial_runs_per_user=2), monkeypatch, [FINISH, FINISH, FINISH])

        first = await api.run()
        second = await api.run()
        third = await api.run()

        assert (first.status_code, second.status_code) == (200, 200)
        assert third.status_code == 402
        assert third.json()["error"]["code"] == "key_required"
        assert third.json()["error"]["message"] == trial_api.RUNS_USED
        assert api.fake.call_count == 2

    async def test_the_beta_as_a_whole_gets_only_so_many(self, monkeypatch, uses) -> None:
        """The total is what bounds the bill."""
        uses.rows.append({"id": "x", "user_id": "someone-else", "kind": "run", "room_id": None})
        api = Api(trial_on(trial_total_runs=1), monkeypatch, [FINISH])

        response = await api.run()

        assert response.status_code == 402
        assert response.json()["error"]["message"] == trial_api.BETA_USED
        assert api.fake.call_count == 0

    async def test_a_refused_run_does_not_spend_a_free_one(self, monkeypatch, uses) -> None:
        """A paused room is refused before the trial is touched."""
        api = Api(trial_on(), monkeypatch, [FINISH])
        paused = make_room()
        paused.room.status = RoomStatus.PAUSED

        async def room(_db, _room_id):
            return paused

        monkeypatch.setattr(runs_api.rooms_repo, "get_room_with_agents", room)

        response = await api.run()

        assert response.status_code == 409
        assert uses.rows == []

    async def test_the_status_counts_down(self, monkeypatch, uses) -> None:
        api = Api(trial_on(trial_runs_per_user=3), monkeypatch, [FINISH])

        before = (await api.get("/api/trial")).json()
        await api.run()
        after = (await api.get("/api/trial")).json()

        assert before == {
            "enabled": True,
            "runs_total": 3,
            "runs_remaining": 3,
            "model": TRIAL_MODEL,
        }
        assert after["runs_remaining"] == 2

    async def test_the_status_never_carries_the_key(self, monkeypatch, uses) -> None:
        api = Api(trial_on(), monkeypatch, [])

        response = await api.get("/api/trial")

        assert OUR_KEY not in response.text


class TestOurKeyFailing:
    @pytest.mark.parametrize("error", [LLMAuthError("no"), LLMCreditError("empty")])
    async def test_the_user_is_not_charged_a_free_run_for_it(
        self, monkeypatch, uses, error
    ) -> None:
        api = Api(trial_on(), monkeypatch, [error])

        response = await api.run()

        assert uses.count("run") == 0
        assert uses.released == ["use-1"]
        # And is not told to check a key they never entered.
        assert finished(response)["detail"] == trial_api.TRIAL_DOWN

    async def test_a_users_own_failing_key_is_reported_as_theirs(
        self, monkeypatch, uses
    ) -> None:
        api = Api(trial_on(), monkeypatch, [LLMAuthError("no")])

        response = await api.run(api_key=USER_KEY)

        assert finished(response)["reason"] == "key_rejected"
        assert finished(response)["detail"] != trial_api.TRIAL_DOWN


class TestHelpers:
    """The agent builder and the objective writer lead up to a run, so a new
    account with no key has to be able to use them too."""

    async def test_the_objective_writer_works_without_a_key(self, monkeypatch, uses) -> None:
        api = Api(trial_on(), monkeypatch, [DRAFT])

        response = await api.draft(model="anthropic/claude-sonnet-5")

        assert response.status_code == 200
        assert response.json()["objective"] == "Write the post."
        assert api.provider["key"] == OUR_KEY
        assert api.provider["model"] == TRIAL_MODEL
        assert uses.count("assist") == 1

    async def test_helper_turns_are_counted_apart_from_runs(self, monkeypatch, uses) -> None:
        """Writing an objective must not use up the runs it was written for."""
        api = Api(trial_on(trial_runs_per_user=1), monkeypatch, [DRAFT, DRAFT, FINISH])

        await api.draft()
        await api.draft()
        response = await api.run()

        assert response.status_code == 200
        assert uses.count("assist") == 2
        assert uses.count("run") == 1

    async def test_helper_turns_run_out_too(self, monkeypatch, uses) -> None:
        api = Api(trial_on(trial_assists_per_user=1), monkeypatch, [DRAFT, DRAFT])

        await api.draft()
        response = await api.draft()

        assert response.status_code == 402
        assert response.json()["error"]["message"] == trial_api.ASSISTS_USED

    async def test_without_a_trial_the_helper_asks_for_a_key(self, monkeypatch, uses) -> None:
        api = Api(settings_with(), monkeypatch, [DRAFT])

        response = await api.draft()

        assert response.status_code == 402
        assert api.fake.call_count == 0

    async def test_our_key_failing_gives_the_turn_back(self, monkeypatch, uses) -> None:
        api = Api(trial_on(), monkeypatch, [LLMCreditError("empty")])

        response = await api.draft()

        assert response.status_code == 402
        assert response.json()["error"]["message"] == trial_api.TRIAL_DOWN
        assert uses.count("assist") == 0
