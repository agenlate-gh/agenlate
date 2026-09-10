"""The roundtable loop, driven end to end with no database and no network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agenlate.llm import FakeLLM, LLMError, Usage
from agenlate.models import (
    Agent,
    Emitter,
    Message,
    MessageCreate,
    Room,
    RoomWithAgents,
    UsageEventCreate,
)
from agenlate.orchestrator import (
    AgentSpoke,
    AgentStarted,
    RunFinished,
    RunResult,
    SupervisorDecided,
    UsageReported,
    run_room,
)
from agenlate.supervisor import RunLimits, SupervisorConfig, TerminationReason

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


class MemoryStore:
    """In-memory RunStore.

    Persistence order matters — a message is written before the event
    announcing it — and that is far easier to verify here than in Supabase.
    """

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.usage: list[UsageEventCreate] = []

    async def append(self, message: MessageCreate) -> Message:
        stored = Message(
            id=f"m{len(self.messages) + 1}",
            seq=len(self.messages) + 1,
            room_id=message.room_id,
            emitter=message.emitter,
            emitter_name=message.emitter_name,
            content=message.content,
            created_at=NOW,
        )
        self.messages.append(stored)
        return stored

    async def record_usage(self, event: UsageEventCreate) -> None:
        self.usage.append(event)


def make_room(count: int = 3) -> RoomWithAgents:
    names = ["Researcher", "Writer", "Critic"]
    agents = [
        Agent(
            id=f"agent-{i + 1}",
            creator_id="u1",
            name=names[i % len(names)],
            role="does work",
            system_prompt="you are a worker",
            created_at=NOW,
            updated_at=NOW,
        )
        for i in range(count)
    ]
    room = Room(
        id="room-1",
        creator_id="u1",
        name="Blog post",
        objective="Write a post about coffee trends",
        created_at=NOW,
        updated_at=NOW,
    )
    return RoomWithAgents(room=room, agents=agents)


def dispatch(agent_id: str, instruction: str) -> str:
    return json.dumps(
        {
            "reasoning": f"Next: {instruction}",
            "action": "dispatch",
            "objective_status": "in_progress",
            "agent_id": agent_id,
            "instruction": instruction,
        }
    )


def finish(message: str = "Here is your post.") -> str:
    return json.dumps(
        {
            "reasoning": "The objective is met.",
            "action": "complete",
            "objective_status": "achieved",
            "message_to_user": message,
        }
    )


def await_user(message: str = "Should I publish this?") -> str:
    return json.dumps(
        {
            "reasoning": "This needs a human decision.",
            "action": "await_user",
            "objective_status": "blocked",
            "message_to_user": message,
        }
    )


async def drain(room, llm, store, **kwargs) -> tuple[list, RunResult]:
    events = [event async for event in run_room(room, [], llm, store, **kwargs)]
    finished = events[-1]
    assert isinstance(finished, RunFinished)
    return events, finished.result


class TestCompleteRun:
    async def test_a_three_agent_room_runs_to_completion(self) -> None:
        """The whole point: supervisor dispatches, agents work, supervisor
        decides it is done."""
        llm = FakeLLM(
            [
                dispatch("agent-1", "Research coffee trends"),
                "I found three trends with sources.",
                dispatch("agent-2", "Write the post"),
                "Here is a 700-word draft.",
                dispatch("agent-3", "Review the draft"),
                "The second section needs a source.",
                finish(),
            ]
        )
        store = MemoryStore()

        events, result = await drain(make_room(), llm, store)

        assert result.reason is TerminationReason.COMPLETED
        assert result.succeeded is True
        assert result.turns == 3
        assert result.final_message == "Here is your post."
        llm.assert_exhausted()

    async def test_the_transcript_is_persisted_in_order(self) -> None:
        llm = FakeLLM(
            [dispatch("agent-1", "Research"), "Found it.", finish()]
        )
        store = MemoryStore()

        await drain(make_room(), llm, store)

        assert [m.emitter for m in store.messages] == [
            Emitter.SUPERVISOR,
            Emitter.AGENT,
            Emitter.SUPERVISOR,
        ]
        assert store.messages[1].content == "Found it."

    async def test_events_arrive_in_the_order_they_happened(self) -> None:
        llm = FakeLLM([dispatch("agent-1", "Research"), "Found it.", finish()])

        events, _ = await drain(make_room(), llm, MemoryStore())

        kinds = [e.type for e in events]
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

    async def test_agent_started_names_the_instruction(self) -> None:
        llm = FakeLLM([dispatch("agent-2", "Write the post"), "Draft.", finish()])

        events, _ = await drain(make_room(), llm, MemoryStore())

        started = next(e for e in events if isinstance(e, AgentStarted))
        assert started.agent_id == "agent-2"
        assert started.agent_name == "Writer"
        assert started.instruction == "Write the post"

    async def test_the_supervisor_sees_what_the_agent_said(self) -> None:
        """Each turn must build on the last, or the roundtable is just
        independent monologues."""
        llm = FakeLLM(
            [dispatch("agent-1", "Research"), "MARKER-FROM-AGENT", finish()]
        )

        await drain(make_room(), llm, MemoryStore())

        final_prompt = llm.calls[-1]["messages"][0]["content"]
        assert "MARKER-FROM-AGENT" in final_prompt

    async def test_await_user_ends_the_run_with_its_message(self) -> None:
        llm = FakeLLM([await_user("Should I publish?")])

        _, result = await drain(make_room(), llm, MemoryStore())

        assert result.reason is TerminationReason.AWAITING_USER
        assert result.succeeded is False
        assert result.summary == "Should I publish?"

    async def test_a_first_turn_completion_needs_no_agents(self) -> None:
        _, result = await drain(make_room(), FakeLLM([finish()]), MemoryStore())

        assert result.reason is TerminationReason.COMPLETED
        assert result.turns == 0


class TestTerminationReasons:
    async def test_max_turns(self) -> None:
        script = []
        for i in range(10):
            script += [dispatch("agent-1", f"step {i}"), f"did step {i}"]
        llm = FakeLLM(script)

        _, result = await drain(
            make_room(), llm, MemoryStore(), limits=RunLimits(max_turns=3)
        )

        assert result.reason is TerminationReason.MAX_TURNS
        assert result.turns == 3

    async def test_spend_cap(self) -> None:
        expensive = Usage.for_call(prompt_tokens=100, completion_tokens=20, cost_usd=0.05)
        script = []
        for i in range(10):
            script += [dispatch("agent-1", f"step {i}"), f"did step {i}"]
        llm = FakeLLM(script, usage_per_call=expensive)

        _, result = await drain(
            make_room(),
            llm,
            MemoryStore(),
            limits=RunLimits(spend_cap_usd=0.12, max_turns=99),
        )

        assert result.reason is TerminationReason.SPEND_CAP
        assert result.usage.cost_usd >= 0.12

    async def test_stalled(self) -> None:
        script = []
        for _ in range(10):
            script += [dispatch("agent-1", "the same thing"), "did it again"]
        llm = FakeLLM(script)

        _, result = await drain(
            make_room(),
            llm,
            MemoryStore(),
            limits=RunLimits(stall_repeat_limit=3, max_turns=99),
        )

        assert result.reason is TerminationReason.STALLED

    async def test_a_stall_stops_before_paying_for_the_repeat(self) -> None:
        """The dispatch is registered before the agent runs, so the third
        identical instruction is caught rather than executed."""
        script = []
        for _ in range(10):
            script += [dispatch("agent-1", "the same thing"), "did it again"]
        llm = FakeLLM(script)

        _, result = await drain(
            make_room(),
            llm,
            MemoryStore(),
            limits=RunLimits(stall_repeat_limit=3, max_turns=99),
        )

        # Two executed turns, then the third dispatch is stopped: 3 supervisor
        # calls and 2 agent calls.
        assert llm.call_count == 5

    async def test_no_progress(self) -> None:
        script = []
        for i in range(10):
            script += [dispatch("agent-1", f"step {i}"), "   "]
        llm = FakeLLM(script)

        _, result = await drain(
            make_room(),
            llm,
            MemoryStore(),
            limits=RunLimits(no_progress_limit=3, max_turns=99),
        )

        assert result.reason is TerminationReason.NO_PROGRESS

    async def test_unpriced_ceiling(self) -> None:
        script = []
        for i in range(20):
            script += [dispatch("agent-1", f"step {i}"), f"did step {i}"]
        llm = FakeLLM(script, usage_per_call=Usage.for_call(cost_usd=None))

        _, result = await drain(
            make_room(),
            llm,
            MemoryStore(),
            limits=RunLimits(unpriced_call_limit=4, max_turns=99),
        )

        assert result.reason is TerminationReason.UNPRICED_CEILING

    async def test_provider_failure_during_the_supervisor_turn(self) -> None:
        llm = FakeLLM([LLMError("OpenRouter returned 402: Insufficient credits")])

        _, result = await drain(make_room(), llm, MemoryStore())

        assert result.reason is TerminationReason.PROVIDER_FAILURE

    async def test_provider_failure_during_an_agent_turn(self) -> None:
        llm = FakeLLM([dispatch("agent-1", "Research"), LLMError("rate limited")])

        _, result = await drain(make_room(), llm, MemoryStore())

        assert result.reason is TerminationReason.PROVIDER_FAILURE

    async def test_supervisor_failure_after_repairs_are_exhausted(self) -> None:
        llm = FakeLLM(["nonsense", "still nonsense", "worse"])

        _, result = await drain(
            make_room(), llm, MemoryStore(), config=SupervisorConfig(max_repair_attempts=2)
        )

        assert result.reason is TerminationReason.SUPERVISOR_FAILURE

    async def test_a_failed_run_still_finishes_cleanly(self) -> None:
        """A provider error must end the run, not escape to the caller."""
        llm = FakeLLM([LLMError("boom")])

        events, result = await drain(make_room(), llm, MemoryStore())

        assert isinstance(events[-1], RunFinished)
        assert result.reason.describe()


class TestEmptyAgentOutput:
    async def test_a_silent_turn_is_written_down(self) -> None:
        """The transcript is what the Supervisor reasons from next. A gap it
        cannot see looks like a step that never happened."""
        llm = FakeLLM([dispatch("agent-1", "Research"), "", finish()])
        store = MemoryStore()

        await drain(make_room(), llm, store)

        assert any(
            m.emitter is Emitter.SYSTEM and "no output" in m.content
            for m in store.messages
        )

    async def test_a_silent_turn_still_costs_money(self) -> None:
        llm = FakeLLM([dispatch("agent-1", "Research"), "", finish()])

        _, result = await drain(make_room(), llm, MemoryStore())

        assert result.usage.calls == 3


class TestBilling:
    async def test_every_call_reaches_the_ledger(self) -> None:
        llm = FakeLLM([dispatch("agent-1", "Research"), "Found it.", finish()])
        store = MemoryStore()

        await drain(make_room(), llm, store, user_id="user-1")

        assert len(store.usage) == 3
        assert all(event.user_id == "user-1" for event in store.usage)
        assert all(event.room_id == "room-1" for event in store.usage)

    async def test_the_ledger_records_the_model(self) -> None:
        llm = FakeLLM([finish()], model="anthropic/claude-sonnet-4.5")
        store = MemoryStore()

        await drain(make_room(), llm, store, user_id="user-1")

        assert store.usage[0].model == "anthropic/claude-sonnet-4.5"

    async def test_supervisor_repairs_are_billed(self) -> None:
        """A rejected reply was paid for. Charging only the successful attempt
        would understate the run."""
        llm = FakeLLM(["not json", finish()])
        store = MemoryStore()

        _, result = await drain(make_room(), llm, store, user_id="user-1")

        assert result.usage.calls == 2

    async def test_unpriced_calls_are_recorded_as_unknown_not_free(self) -> None:
        llm = FakeLLM([finish()], usage_per_call=Usage.for_call(cost_usd=None))
        store = MemoryStore()

        await drain(make_room(), llm, store, user_id="user-1")

        assert store.usage[0].cost_usd is None
        assert store.usage[0].is_priced is False

    async def test_running_totals_are_emitted(self) -> None:
        llm = FakeLLM([dispatch("agent-1", "Research"), "Found it.", finish()])

        events, _ = await drain(make_room(), llm, MemoryStore())

        totals = [e.total.calls for e in events if isinstance(e, UsageReported)]
        assert totals == [1, 2, 3]

    async def test_no_user_id_means_no_ledger_writes(self) -> None:
        """The CLI runs without an account."""
        llm = FakeLLM([finish()])
        store = MemoryStore()

        await drain(make_room(), llm, store)

        assert store.usage == []


class TestPersistenceOrder:
    async def test_a_message_exists_before_its_event_is_yielded(self) -> None:
        """A client acting on an event must be able to find the message it
        names."""
        llm = FakeLLM([dispatch("agent-1", "Research"), "Found it.", finish()])
        store = MemoryStore()

        seen: list[str] = []
        async for event in run_room(make_room(), [], llm, store):
            if isinstance(event, (SupervisorDecided, AgentSpoke)):
                assert event.message.id in {m.id for m in store.messages}
                seen.append(event.message.id)

        assert len(seen) == 3


class TestExistingTranscript:
    async def test_a_run_resumes_from_prior_messages(self) -> None:
        prior = [
            Message(
                id="m0",
                seq=1,
                room_id="room-1",
                emitter=Emitter.USER,
                emitter_name="Alice",
                content="EARLIER-CONTEXT",
                created_at=NOW,
            )
        ]
        llm = FakeLLM([finish()])

        events = [e async for e in run_room(make_room(), prior, llm, MemoryStore())]

        assert "EARLIER-CONTEXT" in llm.calls[0]["messages"][0]["content"]
        assert isinstance(events[-1], RunFinished)
