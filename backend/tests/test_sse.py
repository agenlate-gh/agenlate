"""Server-sent event streaming.

The heartbeat logic is the part worth testing hard: the obvious
implementation silently cancels the run it is meant to keep alive.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from agenlate.api.sse import HEARTBEAT_SECONDS, encode, heartbeat, stream, to_payload
from agenlate.llm import Usage
from agenlate.models import Emitter, Message
from agenlate.orchestrator import (
    AgentSpoke,
    AgentStarted,
    RunFinished,
    RunResult,
    SupervisorDecided,
    UsageReported,
)
from agenlate.supervisor import TerminationReason
from agenlate.supervisor.contract import SupervisorDecision

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def message(content: str = "hello") -> Message:
    return Message(
        id="m1",
        seq=1,
        room_id="r1",
        emitter=Emitter.AGENT,
        emitter_name="Researcher",
        content=content,
        created_at=NOW,
    )


def dispatch_decision() -> SupervisorDecision:
    return SupervisorDecision(
        reasoning="Research first.",
        action="dispatch",
        objective_status="in_progress",
        agent_id="agent-1",
        instruction="Find sources",
    )


async def emit(*events, delay: float = 0.0):
    for event in events:
        if delay:
            await asyncio.sleep(delay)
        yield event


def parse(chunk: str) -> tuple[str, dict]:
    lines = chunk.strip().split("\n")
    event_type = lines[0].removeprefix("event: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    return event_type, payload


class TestWireFormat:
    def test_encodes_an_event_and_terminates_it(self) -> None:
        chunk = encode("agent_message", {"a": 1})

        assert chunk.startswith("event: agent_message\n")
        assert chunk.endswith("\n\n")  # SSE frames end on a blank line

    def test_payload_is_json(self) -> None:
        event_type, payload = parse(encode("usage", {"cost_usd": 0.01}))

        assert event_type == "usage"
        assert payload == {"cost_usd": 0.01}

    def test_heartbeat_is_a_comment(self) -> None:
        """Clients ignore comments; proxies see traffic."""
        assert heartbeat().startswith(":")
        assert heartbeat().endswith("\n\n")


class TestPayloads:
    def test_supervisor_decision_carries_its_reasoning(self) -> None:
        """The reasoning is the part users find compelling, so it is a
        first-class field rather than buried in the message."""
        payload = to_payload(
            SupervisorDecided(decision=dispatch_decision(), message=message(), attempts=1)
        )

        assert payload["reasoning"] == "Research first."
        assert payload["action"] == "dispatch"
        assert payload["agent_id"] == "agent-1"
        assert payload["instruction"] == "Find sources"

    def test_a_repaired_decision_reports_its_attempts(self) -> None:
        payload = to_payload(
            SupervisorDecided(decision=dispatch_decision(), message=message(), attempts=3)
        )

        assert payload["attempts"] == 3

    def test_agent_started_names_the_agent_and_task(self) -> None:
        payload = to_payload(
            AgentStarted(agent_id="a1", agent_name="Researcher", instruction="Find it")
        )

        assert payload == {
            "agent_id": "a1",
            "agent_name": "Researcher",
            "instruction": "Find it",
        }

    def test_agent_message_carries_the_stored_message(self) -> None:
        payload = to_payload(AgentSpoke(agent_id="a1", message=message("found it")))

        assert payload["message"]["content"] == "found it"
        assert payload["message"]["seq"] == 1

    def test_usage_reports_both_the_call_and_the_running_total(self) -> None:
        """The interface shows a live cost, which needs the total, and the
        per-call figure makes an expensive turn visible."""
        payload = to_payload(
            UsageReported(
                usage=Usage.for_call(prompt_tokens=100, completion_tokens=20, cost_usd=0.01),
                total=Usage.for_call(prompt_tokens=500, completion_tokens=60, cost_usd=0.05),
            )
        )

        assert payload["call"]["cost_usd"] == 0.01
        assert payload["total"]["cost_usd"] == 0.05

    def test_usage_surfaces_unknown_cost(self) -> None:
        payload = to_payload(
            UsageReported(
                usage=Usage.for_call(cost_usd=None),
                total=Usage.for_call(cost_usd=None) + Usage.for_call(cost_usd=0.01),
            )
        )

        assert payload["total"]["has_unknown_cost"] is True
        assert payload["total"]["unpriced_calls"] == 1

    def test_run_finished_explains_itself_in_plain_language(self) -> None:
        """Shown directly to a non-technical user, so the reason code alone
        is not enough."""
        payload = to_payload(
            RunFinished(
                result=RunResult(
                    reason=TerminationReason.SPEND_CAP,
                    turns=4,
                    usage=Usage.for_call(cost_usd=0.5),
                    messages_added=8,
                )
            )
        )

        assert payload["reason"] == "spend_cap"
        assert "spending limit" in payload["explanation"]
        assert payload["succeeded"] is False

    def test_a_provider_failure_passes_on_the_detail(self) -> None:
        payload = to_payload(
            RunFinished(
                result=RunResult(
                    reason=TerminationReason.PROVIDER_FAILURE,
                    turns=1,
                    usage=Usage(),
                    messages_added=1,
                    detail="OpenRouter returned 402: Insufficient credits",
                )
            )
        )

        assert "402" in payload["detail"]


class TestStreaming:
    async def test_events_arrive_in_order(self) -> None:
        events = emit(
            AgentStarted(agent_id="a1", agent_name="R", instruction="go"),
            AgentSpoke(agent_id="a1", message=message()),
        )

        chunks = [c async for c in stream(events) if not c.startswith(":")]

        assert [parse(c)[0] for c in chunks] == ["agent_started", "agent_message"]

    async def test_an_empty_run_streams_nothing(self) -> None:
        chunks = [c async for c in stream(emit())]

        assert chunks == []

    async def test_a_quiet_stretch_produces_a_heartbeat(self, monkeypatch) -> None:
        """An agent turn with several web searches easily runs past a minute
        without producing an event, and proxies drop idle connections."""
        monkeypatch.setattr("agenlate.api.sse.HEARTBEAT_SECONDS", 0.05)

        chunks = [
            c
            async for c in stream(
                emit(AgentStarted(agent_id="a1", agent_name="R", instruction="go"), delay=0.2)
            )
        ]

        assert any(c.startswith(":") for c in chunks)
        assert any(c.startswith("event:") for c in chunks)

    async def test_a_heartbeat_does_not_cancel_the_run(self, monkeypatch) -> None:
        """The reason this module exists. Wrapping each step in wait_for would
        cancel the in-flight turn on every heartbeat, silently killing the work
        the heartbeat was meant to protect."""
        monkeypatch.setattr("agenlate.api.sse.HEARTBEAT_SECONDS", 0.02)
        produced: list[str] = []

        async def slow():
            for i in range(3):
                await asyncio.sleep(0.1)
                produced.append(f"event-{i}")
                yield AgentStarted(agent_id="a1", agent_name="R", instruction=f"step {i}")

        chunks = [c async for c in stream(slow()) if c.startswith("event:")]

        assert len(chunks) == 3
        assert produced == ["event-0", "event-1", "event-2"]

    async def test_abandoning_the_stream_cancels_the_run(self) -> None:
        """A client that disconnects must not leave a run spending the user's
        credit with nobody watching."""
        cancelled = asyncio.Event()

        async def long_run():
            try:
                yield AgentStarted(agent_id="a1", agent_name="R", instruction="go")
                await asyncio.sleep(10)
                yield AgentStarted(agent_id="a1", agent_name="R", instruction="never")
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                cancelled.set()

        generator = stream(long_run())
        first = await generator.__anext__()
        assert first.startswith("event:")

        await generator.aclose()

        assert cancelled.is_set()


class TestHeartbeatInterval:
    def test_is_short_enough_for_common_proxy_timeouts(self) -> None:
        """Most proxies drop an idle connection somewhere around 30 to 60
        seconds."""
        assert HEARTBEAT_SECONDS <= 30
