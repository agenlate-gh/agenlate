"""The conversation that writes a room's objective.

A new user has to write the objective before anything happens, and the
Supervisor reads it before every decision. Most people know what they want and
not how to put it so a coordinator can tell when it is done.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.auth import CurrentUser, current_user
from agenlate.llm import FakeLLM, Usage
from agenlate.main import create_app
from agenlate.models import OBJECTIVE_MAX
from agenlate.objective import (
    NO_NAME_YET,
    NO_OBJECTIVE_YET,
    ObjectiveError,
    build_messages,
    refine_objective,
)

KEY = "sk-or-v1-" + "0123456789abcdef" * 3


def wrote(objective: str, name: str | None = None, reply: str = "Written.") -> str:
    return json.dumps(
        {"reply": reply, "objective": objective, "name": name, "needs_answer": False}
    )


def asked(question: str) -> str:
    return json.dumps({"reply": question, "objective": None, "needs_answer": True})


async def turn(llm, **kwargs):
    defaults = dict(
        name=None,
        objective=None,
        conversation=[{"role": "user", "content": "I want a blog post about coffee"}],
    )
    return await refine_objective(llm, **{**defaults, **kwargs})


class TestContext:
    def test_an_unnamed_room_asks_for_a_name(self) -> None:
        _, messages = build_messages(None, None, [])

        assert NO_NAME_YET in messages[0]["content"]
        assert NO_OBJECTIVE_YET in messages[0]["content"]

    def test_the_current_draft_is_shown_so_it_can_be_revised(self) -> None:
        """Revising means keeping what the user did not ask to change, which
        needs the current text in front of the model."""
        _, messages = build_messages("Coffee", "Write 600 words on cold brew.", [])

        assert "Write 600 words on cold brew." in messages[0]["content"]

    def test_the_conversation_is_included_in_order(self) -> None:
        _, messages = build_messages(
            None,
            None,
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "second"},
            ],
        )

        content = messages[0]["content"]
        assert content.index("first") < content.index("second")

    def test_the_helper_is_told_what_the_coordinator_needs(self) -> None:
        system, _ = build_messages(None, None, [])

        assert "how to know it is finished" in system

    def test_the_helper_is_told_not_to_invent_facts(self) -> None:
        system, _ = build_messages(None, None, [])

        assert "Never invent facts" in system


class TestTurns:
    async def test_a_clear_request_produces_an_objective_and_a_name(self) -> None:
        llm = FakeLLM([wrote("Write a 600-word post on cold brew.", name="Coffee post")])

        result = await turn(llm)

        assert result.reply.objective == "Write a 600-word post on cold brew."
        assert result.reply.name == "Coffee post"

    async def test_an_ambiguous_request_asks_rather_than_guesses(self) -> None:
        llm = FakeLLM([asked("Who is the post for?")])

        result = await turn(llm)

        assert result.reply.needs_answer is True
        assert result.reply.objective is None

    async def test_a_named_room_keeps_its_name(self) -> None:
        """A model that offers a name anyway would rename a room the user
        already named."""
        llm = FakeLLM([wrote("Revised.", name="Something else")])

        result = await turn(llm, name="Q3 launch")

        assert result.reply.name is None

    async def test_a_malformed_reply_is_repaired_once(self) -> None:
        llm = FakeLLM(["not json", wrote("Fixed.")])

        result = await turn(llm)

        assert result.reply.objective == "Fixed."
        assert result.attempts == 2

    async def test_it_gives_up_rather_than_inventing_an_objective(self) -> None:
        with pytest.raises(ObjectiveError):
            await turn(FakeLLM(["nope", "still nope"]))

    async def test_an_objective_longer_than_a_room_can_hold_is_refused(self) -> None:
        """The draft goes straight into the room form, so one the database
        would reject is not a draft."""
        too_long = "x" * (OBJECTIVE_MAX + 1)
        with pytest.raises(ObjectiveError):
            await turn(FakeLLM([wrote(too_long), wrote(too_long)]))

    async def test_a_repaired_turn_charges_for_both_calls(self) -> None:
        llm = FakeLLM(
            ["not json", wrote("Fixed.")],
            usage_per_call=Usage.for_call(prompt_tokens=10, completion_tokens=5, cost_usd=0.001),
        )

        result = await turn(llm)

        assert result.usage.cost_usd == pytest.approx(0.002)


class TestEndpoint:
    @pytest.fixture
    async def api(self, settings, monkeypatch):
        app = create_app(settings)
        app.dependency_overrides[current_user] = lambda: CurrentUser(
            id="u1", email="u1@example.com"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    def use_model(self, monkeypatch, script: list[str]) -> None:
        fake = FakeLLM(script)
        monkeypatch.setattr("agenlate.api.objective.OpenRouterClient", lambda *a, **k: fake)

    async def test_it_returns_a_draft_without_saving_anything(self, api, monkeypatch) -> None:
        self.use_model(monkeypatch, [wrote("Write the post.", name="Coffee")])

        response = await api.post(
            "/api/rooms/objective-draft",
            json={
                "api_key": KEY,
                "conversation": [{"role": "user", "content": "a coffee blog post"}],
            },
        )

        assert response.status_code == 200
        assert response.json()["objective"] == "Write the post."
        assert response.json()["name"] == "Coffee"

    async def test_a_malformed_key_is_refused_before_any_model_call(self, api) -> None:
        response = await api.post(
            "/api/rooms/objective-draft", json={"api_key": "not-a-key", "conversation": []}
        )

        assert response.status_code == 422
        assert "not-a-key" not in response.text

    async def test_a_model_that_cannot_answer_is_a_502_not_a_crash(
        self, api, monkeypatch
    ) -> None:
        self.use_model(monkeypatch, ["nope", "still nope"])

        response = await api.post(
            "/api/rooms/objective-draft",
            json={"api_key": KEY, "conversation": [{"role": "user", "content": "x"}]},
        )

        assert response.status_code == 502

    async def test_it_requires_a_signed_in_caller(self, settings) -> None:
        app = create_app(settings)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/rooms/objective-draft", json={"api_key": KEY, "conversation": []}
            )

        assert response.status_code == 401
