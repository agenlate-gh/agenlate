"""Domain model behaviour. No database, no network."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agenlate.models import (
    Agent,
    AgentCreate,
    Emitter,
    Message,
    Room,
    RoomWithAgents,
    UsageEventCreate,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def make_agent(agent_id: str = "a1", name: str = "Researcher") -> Agent:
    return Agent(
        id=agent_id,
        creator_id="u1",
        name=name,
        role="finds and verifies information",
        system_prompt="you research",
        created_at=NOW,
        updated_at=NOW,
    )


def make_room() -> Room:
    return Room(
        id="r1",
        creator_id="u1",
        name="Blog post",
        objective="Write a post about coffee trends",
        created_at=NOW,
        updated_at=NOW,
    )


class TestCapabilityLine:
    def test_contains_what_the_supervisor_needs_to_dispatch(self) -> None:
        line = make_agent().capability_line()

        assert "id=a1" in line
        assert "Researcher" in line
        assert "finds and verifies information" in line

    def test_stays_on_one_line(self) -> None:
        """The roster is re-sent every turn; stray newlines corrupt the prompt."""
        agent = make_agent(name="Multi\nLine")

        assert "\n" not in agent.capability_line().replace("Multi\nLine", "")

    def test_excludes_the_system_prompt(self) -> None:
        """System prompts run to thousands of characters and are re-sent per
        turn. Including one here would multiply directly into token cost."""
        agent = make_agent()
        agent.system_prompt = "SECRET_MARKER" + "x" * 4000

        assert "SECRET_MARKER" not in agent.capability_line()


class TestMessageRender:
    def test_attributes_the_speaker(self) -> None:
        message = Message(
            id="m1",
            seq=1,
            room_id="r1",
            emitter=Emitter.AGENT,
            emitter_name="Researcher",
            content="Here is what I found",
            created_at=NOW,
        )

        assert message.render() == "[Researcher]: Here is what I found"


class TestRoomWithAgents:
    def test_resolves_a_dispatch_target(self) -> None:
        room = RoomWithAgents(room=make_room(), agents=[make_agent("a1"), make_agent("a2")])

        assert room.agent_by_id("a2") is not None
        assert room.agent_by_id("a2").id == "a2"

    def test_unknown_agent_returns_none_rather_than_raising(self) -> None:
        """A hallucinated agent id is an expected model failure that the
        Supervisor repairs, not an exceptional condition."""
        room = RoomWithAgents(room=make_room(), agents=[make_agent("a1")])

        assert room.agent_by_id("does-not-exist") is None

    def test_roster_lists_every_agent(self) -> None:
        room = RoomWithAgents(
            room=make_room(),
            agents=[make_agent("a1", "Researcher"), make_agent("a2", "Writer")],
        )
        roster = room.roster()

        assert roster.count("\n") == 1
        assert "Researcher" in roster and "Writer" in roster


class TestAgentCreate:
    def test_rejects_an_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            AgentCreate(name="", role="r", system_prompt="p")

    def test_rejects_a_system_prompt_over_the_column_limit(self) -> None:
        """Mirrors the database check constraint, so the user gets a usable
        error instead of a constraint violation from Postgres."""
        with pytest.raises(ValidationError):
            AgentCreate(name="n", role="r", system_prompt="x" * 8001)


class TestUsageEventCreate:
    def test_reported_cost_is_priced(self) -> None:
        event = UsageEventCreate(user_id="u1", model="m", cost_usd=0.0012)

        assert event.is_priced is True

    def test_missing_cost_is_not_priced(self) -> None:
        event = UsageEventCreate(user_id="u1", model="m", cost_usd=None)

        assert event.is_priced is False
        assert event.cost_usd is None

    def test_zero_cost_is_still_priced(self) -> None:
        """A provider reporting exactly zero is different from reporting
        nothing. Free requests exist; unknown cost must never masquerade as
        one."""
        event = UsageEventCreate(user_id="u1", model="m", cost_usd=0.0)

        assert event.is_priced is True

    def test_negative_cost_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageEventCreate(user_id="u1", model="m", cost_usd=-1)
