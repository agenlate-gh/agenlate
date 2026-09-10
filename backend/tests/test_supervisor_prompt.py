"""Supervisor prompt assembly and context budgeting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agenlate.models import Agent, Emitter, Message, Room, RoomWithAgents
from agenlate.supervisor.prompt import (
    EMPTY_TRANSCRIPT,
    PromptBudget,
    build_supervisor_messages,
    build_system_prompt,
    estimate_tokens,
    render_history,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
OBJECTIVE = "Write a 700-word blog post about coffee shop trends in 2026"


def make_room(agent_count: int = 2) -> RoomWithAgents:
    agents = [
        Agent(
            id=f"agent-{i}",
            creator_id="u1",
            name=f"Worker {i}",
            role=f"role number {i}",
            system_prompt="x" * 3000,  # long on purpose: must not reach the prompt
            created_at=NOW,
            updated_at=NOW,
        )
        for i in range(agent_count)
    ]
    room = Room(
        id="r1",
        creator_id="u1",
        name="Blog post",
        objective=OBJECTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    return RoomWithAgents(room=room, agents=agents)


def make_messages(count: int, *, size: int = 40) -> list[Message]:
    return [
        Message(
            id=f"m{i}",
            seq=i + 1,
            room_id="r1",
            emitter=Emitter.AGENT,
            emitter_name=f"Worker {i % 2}",
            content=f"message {i} " + "x" * size,
            created_at=NOW + timedelta(seconds=i),
        )
        for i in range(count)
    ]


class TestTokenEstimate:
    def test_empty_text_costs_nothing(self) -> None:
        assert estimate_tokens("") == 0

    def test_grows_with_length(self) -> None:
        assert estimate_tokens("x" * 1000) > estimate_tokens("x" * 100)

    def test_leans_high_rather_than_low(self) -> None:
        """Underestimating risks overflowing the context window and failing the
        call outright. Overestimating only trims a little extra history."""
        text = "x" * 1000
        naive = len(text) // 4

        assert estimate_tokens(text) > naive


class TestSystemPrompt:
    def test_carries_the_objective_verbatim(self) -> None:
        assert OBJECTIVE in build_system_prompt(make_room())

    def test_lists_every_agent(self) -> None:
        prompt = build_system_prompt(make_room(agent_count=3))

        for i in range(3):
            assert f"agent-{i}" in prompt

    def test_excludes_agent_system_prompts(self) -> None:
        """The roster is re-sent every turn. Including each agent's full system
        prompt would multiply thousands of characters by the turn count."""
        prompt = build_system_prompt(make_room())

        assert "x" * 3000 not in prompt

    def test_includes_the_decision_schema(self) -> None:
        prompt = build_system_prompt(make_room())

        assert "dispatch" in prompt
        assert "await_user" in prompt
        assert "objective_status" in prompt

    def test_explains_each_action(self) -> None:
        prompt = build_system_prompt(make_room())

        assert '"dispatch"' in prompt
        assert '"complete"' in prompt
        assert '"await_user"' in prompt

    def test_forbids_inventing_agent_ids(self) -> None:
        assert "Do not invent one" in build_system_prompt(make_room())

    def test_a_room_with_no_agents_says_so(self) -> None:
        """Better than an empty section, which reads as a formatting bug."""
        prompt = build_system_prompt(make_room(agent_count=0))

        assert "no agents assigned" in prompt


class TestHistoryRendering:
    def test_no_messages_reads_as_a_first_turn(self) -> None:
        transcript, omitted = render_history([])

        assert transcript == EMPTY_TRANSCRIPT
        assert omitted == 0

    def test_short_history_is_kept_whole(self) -> None:
        transcript, omitted = render_history(make_messages(5))

        assert omitted == 0
        for i in range(5):
            assert f"message {i} " in transcript

    def test_messages_are_attributed(self) -> None:
        transcript, _ = render_history(make_messages(2))

        assert "[Worker 0]:" in transcript

    def test_order_is_preserved(self) -> None:
        transcript, _ = render_history(make_messages(5))

        positions = [transcript.index(f"message {i} ") for i in range(5)]
        assert positions == sorted(positions)


class TestBudgeting:
    def test_long_history_is_truncated(self) -> None:
        budget = PromptBudget(history_tokens=300, head_messages=2, min_tail_messages=2)

        transcript, omitted = render_history(make_messages(100), budget)

        assert omitted > 0
        assert estimate_tokens(transcript) < 1000

    def test_earliest_messages_survive(self) -> None:
        """They frame what the room is doing."""
        budget = PromptBudget(history_tokens=200, head_messages=2, min_tail_messages=2)

        transcript, _ = render_history(make_messages(100), budget)

        assert "message 0 " in transcript
        assert "message 1 " in transcript

    def test_most_recent_messages_survive(self) -> None:
        """They are what the next decision responds to."""
        budget = PromptBudget(history_tokens=200, head_messages=2, min_tail_messages=2)

        transcript, _ = render_history(make_messages(100), budget)

        assert "message 99 " in transcript
        assert "message 98 " in transcript

    def test_the_middle_is_what_goes(self) -> None:
        budget = PromptBudget(history_tokens=200, head_messages=2, min_tail_messages=2)

        transcript, _ = render_history(make_messages(100), budget)

        assert "message 50 " not in transcript

    def test_the_gap_is_marked(self) -> None:
        """A Supervisor that cannot see the gap assumes the transcript is
        complete, and reasons from a false premise."""
        budget = PromptBudget(history_tokens=200, head_messages=2, min_tail_messages=2)

        transcript, omitted = render_history(make_messages(100), budget)

        assert "omitted to stay within context" in transcript
        assert str(omitted) in transcript

    def test_the_marker_counts_what_actually_went(self) -> None:
        budget = PromptBudget(history_tokens=200, head_messages=2, min_tail_messages=2)
        messages = make_messages(100)

        transcript, omitted = render_history(messages, budget)

        kept = sum(1 for i in range(100) if f"message {i} " in transcript)
        assert kept + omitted == 100

    def test_recency_wins_over_the_ceiling(self) -> None:
        """A Supervisor that cannot see what just happened cannot decide what
        comes next, so the tail minimum overrides the budget."""
        budget = PromptBudget(history_tokens=1, head_messages=1, min_tail_messages=3)

        transcript, _ = render_history(make_messages(20, size=400), budget)

        for i in (17, 18, 19):
            assert f"message {i} " in transcript

    def test_a_generous_budget_elides_nothing(self) -> None:
        budget = PromptBudget(history_tokens=1_000_000)

        transcript, omitted = render_history(make_messages(50), budget)

        assert omitted == 0
        assert "omitted" not in transcript

    def test_truncation_scales_with_history_length(self) -> None:
        """The real failure mode: cost growing with every turn."""
        budget = PromptBudget(history_tokens=300, head_messages=2, min_tail_messages=2)

        short, _ = render_history(make_messages(10), budget)
        long, _ = render_history(make_messages(500), budget)

        assert estimate_tokens(long) < estimate_tokens(short) * 3


class TestAssembledMessages:
    def test_returns_a_system_prompt_and_one_user_message(self) -> None:
        system, messages = build_supervisor_messages(make_room(), make_messages(3))

        assert OBJECTIVE in system
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_the_transcript_travels_in_the_user_message(self) -> None:
        _, messages = build_supervisor_messages(make_room(), make_messages(3))

        assert "message 0 " in messages[0]["content"]

    def test_the_objective_survives_heavy_truncation(self) -> None:
        """The objective lives in the system prompt precisely so that no amount
        of history truncation can put it at risk."""
        budget = PromptBudget(history_tokens=1, head_messages=1, min_tail_messages=1)

        system, messages = build_supervisor_messages(
            make_room(), make_messages(500, size=400), budget
        )

        assert OBJECTIVE in system
        assert "agent-0" in system

    def test_the_first_turn_still_asks_for_a_decision(self) -> None:
        _, messages = build_supervisor_messages(make_room(), [])

        assert EMPTY_TRANSCRIPT in messages[0]["content"]
        assert "your next decision" in messages[0]["content"].lower()
