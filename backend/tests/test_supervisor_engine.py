"""The Supervisor engine: validation, repair, and refusing to guess."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agenlate.llm import FakeLLM, LLMError, Usage
from agenlate.models import Agent, Emitter, Message, Room, RoomWithAgents
from agenlate.supervisor.contract import SupervisorAction
from agenlate.supervisor.supervisor import (
    Supervisor,
    SupervisorConfig,
    SupervisorError,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def make_room(agent_ids: tuple[str, ...] = ("agent-1", "agent-2")) -> RoomWithAgents:
    agents = [
        Agent(
            id=agent_id,
            creator_id="u1",
            name=f"Worker {i}",
            role="does work",
            system_prompt="p",
            created_at=NOW,
            updated_at=NOW,
        )
        for i, agent_id in enumerate(agent_ids)
    ]
    room = Room(
        id="r1",
        creator_id="u1",
        name="Room",
        objective="Write a blog post",
        created_at=NOW,
        updated_at=NOW,
    )
    return RoomWithAgents(room=room, agents=agents)


def history(count: int = 1) -> list[Message]:
    return [
        Message(
            id=f"m{i}",
            seq=i + 1,
            room_id="r1",
            emitter=Emitter.USER,
            emitter_name="Alice",
            content=f"message {i}",
            created_at=NOW,
        )
        for i in range(count)
    ]


def dispatch_json(agent_id: str = "agent-1", instruction: str = "Do the research") -> str:
    return json.dumps(
        {
            "reasoning": "Research is needed first.",
            "action": "dispatch",
            "objective_status": "in_progress",
            "agent_id": agent_id,
            "instruction": instruction,
        }
    )


COMPLETE_JSON = json.dumps(
    {
        "reasoning": "The objective is met.",
        "action": "complete",
        "objective_status": "achieved",
        "message_to_user": "Here is your post.",
    }
)


class TestCleanDecision:
    async def test_a_valid_reply_stands(self) -> None:
        llm = FakeLLM([dispatch_json()])
        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.decision.action is SupervisorAction.DISPATCH
        assert turn.decision.agent_id == "agent-1"
        assert turn.attempts == 1
        assert turn.needed_repair is False
        llm.assert_exhausted()

    async def test_a_terminal_decision_is_returned(self) -> None:
        turn = await Supervisor(FakeLLM([COMPLETE_JSON])).decide(make_room(), history())

        assert turn.decision.is_terminal is True
        assert turn.decision.message_to_user == "Here is your post."

    async def test_asks_for_json_mode_at_zero_temperature(self) -> None:
        """Turn-taking is a decision, not a creative act."""
        llm = FakeLLM([dispatch_json()])
        await Supervisor(llm).decide(make_room(), history())

        assert llm.last_call["json_mode"] is True
        assert llm.last_call["temperature"] == 0.0

    async def test_the_objective_and_roster_reach_the_model(self) -> None:
        llm = FakeLLM([dispatch_json()])
        await Supervisor(llm).decide(make_room(), history())

        system = llm.last_call["system"]
        assert "Write a blog post" in system
        assert "agent-1" in system and "agent-2" in system


class TestLocalRecovery:
    """Recoveries that need no round trip. Each one saves the user a repair."""

    async def test_markdown_fences_are_stripped(self) -> None:
        llm = FakeLLM([f"```json\n{dispatch_json()}\n```"])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 1  # no repair was needed
        assert turn.decision.agent_id == "agent-1"

    async def test_bare_fences_are_stripped(self) -> None:
        llm = FakeLLM([f"```\n{dispatch_json()}\n```"])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 1

    async def test_json_wrapped_in_commentary_is_found(self) -> None:
        llm = FakeLLM([f"Sure! Here is my decision:\n{dispatch_json()}\nLet me know."])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 1
        assert turn.decision.agent_id == "agent-1"

    async def test_surrounding_whitespace_is_ignored(self) -> None:
        llm = FakeLLM([f"\n\n  {dispatch_json()}  \n"])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 1


class TestRepair:
    async def test_malformed_json_is_repaired(self) -> None:
        llm = FakeLLM(["this is not json at all", dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 2
        assert turn.needed_repair is True
        assert turn.decision.agent_id == "agent-1"
        llm.assert_exhausted()

    async def test_a_schema_violation_is_repaired(self) -> None:
        """Dispatch without an agent_id: valid JSON, invalid decision."""
        broken = json.dumps(
            {
                "reasoning": "Research first.",
                "action": "dispatch",
                "objective_status": "in_progress",
            }
        )
        llm = FakeLLM([broken, dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 2

    async def test_an_invented_field_is_repaired(self) -> None:
        invented = json.dumps(
            {
                "reasoning": "Research first.",
                "action": "dispatch",
                "objective_status": "in_progress",
                "agent_id": "agent-1",
                "instruction": "go",
                "confidence": 0.9,
            }
        )
        llm = FakeLLM([invented, dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 2

    async def test_a_hallucinated_agent_id_is_repaired(self) -> None:
        """Validity depends on this room's roster, which the schema cannot
        express, so it is checked here."""
        llm = FakeLLM([dispatch_json(agent_id="agent-99"), dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 2
        assert turn.decision.agent_id == "agent-1"

    async def test_an_empty_reply_is_repaired(self) -> None:
        llm = FakeLLM(["", dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 2

    async def test_a_json_array_is_repaired(self) -> None:
        """Valid JSON, wrong shape."""
        llm = FakeLLM(['[{"action": "dispatch"}]', dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 2

    async def test_two_repairs_are_allowed_by_default(self) -> None:
        llm = FakeLLM(["nonsense", "still nonsense", dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 3
        llm.assert_exhausted()


class TestRepairPrompt:
    async def test_the_rejected_output_is_shown_back(self) -> None:
        llm = FakeLLM(["I think agent one should go next", dispatch_json()])

        await Supervisor(llm).decide(make_room(), history())

        repair = llm.calls[1]["messages"]
        assert any(
            m["role"] == "assistant" and "agent one should go next" in m["content"]
            for m in repair
        )

    async def test_the_specific_error_is_quoted(self) -> None:
        """A generic 'try again' produces a re-roll; a specific error produces
        a correction."""
        broken = json.dumps(
            {"reasoning": "r", "action": "dispatch", "objective_status": "in_progress"}
        )
        llm = FakeLLM([broken, dispatch_json()])

        await Supervisor(llm).decide(make_room(), history())

        repair_text = llm.calls[1]["messages"][-1]["content"]
        assert "agent_id" in repair_text

    async def test_a_hallucinated_id_repair_lists_the_real_ones(self) -> None:
        llm = FakeLLM([dispatch_json(agent_id="agent-99"), dispatch_json()])

        await Supervisor(llm).decide(make_room(), history())

        repair_text = llm.calls[1]["messages"][-1]["content"]
        assert "agent-99" in repair_text
        assert "agent-1" in repair_text and "agent-2" in repair_text

    async def test_a_huge_rejected_reply_is_truncated(self) -> None:
        """Echoing the whole thing back pays for it twice."""
        llm = FakeLLM(["x" * 50_000, dispatch_json()])

        await Supervisor(llm).decide(make_room(), history())

        echoed = llm.calls[1]["messages"][-2]["content"]
        assert len(echoed) < 2_000
        assert "truncated" in echoed


class TestFailingClosed:
    async def test_exhausting_repairs_raises(self) -> None:
        llm = FakeLLM(["bad", "worse", "worst"])

        with pytest.raises(SupervisorError, match="no valid decision"):
            await Supervisor(llm).decide(make_room(), history())

    async def test_the_failure_names_the_last_error(self) -> None:
        llm = FakeLLM(["bad", "worse", "worst"])

        with pytest.raises(SupervisorError, match="not valid JSON"):
            await Supervisor(llm).decide(make_room(), history())

    async def test_it_never_falls_back_to_a_guess(self) -> None:
        """A fabricated decision would dispatch work nobody asked for."""
        llm = FakeLLM(["bad", "worse", "worst"])

        with pytest.raises(SupervisorError):
            await Supervisor(llm).decide(make_room(), history())

    async def test_the_repair_budget_is_configurable(self) -> None:
        config = SupervisorConfig(max_repair_attempts=0)
        llm = FakeLLM(["bad", dispatch_json()])

        with pytest.raises(SupervisorError):
            await Supervisor(llm, config).decide(make_room(), history())

        assert llm.call_count == 1

    async def test_a_provider_failure_is_not_treated_as_repairable(self) -> None:
        """Re-prompting cannot fix an invalid key or a rate limit, and trying
        would spend the repair budget on something no repair can address."""
        llm = FakeLLM([LLMError("OpenRouter returned 402: Insufficient credits")])

        with pytest.raises(LLMError, match="402"):
            await Supervisor(llm).decide(make_room(), history())

        assert llm.call_count == 1


class TestUsageAccounting:
    async def test_a_clean_decision_reports_its_usage(self) -> None:
        llm = FakeLLM([dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.usage.calls == 1
        assert turn.usage.total_tokens > 0

    async def test_failed_attempts_are_still_charged(self) -> None:
        """A rejected reply cost money. Counting only the successful attempt
        would understate the run and quietly break the spend cap."""
        llm = FakeLLM(["bad", "also bad", dispatch_json()])

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.attempts == 3
        assert turn.usage.calls == 3

    async def test_usage_sums_across_repairs(self) -> None:
        per_call = Usage.for_call(prompt_tokens=100, completion_tokens=20, cost_usd=0.001)
        llm = FakeLLM(["bad", dispatch_json()], usage_per_call=per_call)

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.usage.cost_usd == pytest.approx(0.002)
        assert turn.usage.total_tokens == 240

    async def test_unpriced_repairs_are_counted_as_unknown(self) -> None:
        llm = FakeLLM(
            ["bad", dispatch_json()], usage_per_call=Usage.for_call(cost_usd=None)
        )

        turn = await Supervisor(llm).decide(make_room(), history())

        assert turn.usage.unpriced_calls == 2
        assert turn.usage.has_unknown_cost is True


class TestFirstTurn:
    async def test_works_with_an_empty_transcript(self) -> None:
        turn = await Supervisor(FakeLLM([dispatch_json()])).decide(make_room(), [])

        assert turn.decision.is_dispatch

    async def test_a_room_with_one_agent_still_validates_the_id(self) -> None:
        room = make_room(agent_ids=("only-one",))
        llm = FakeLLM([dispatch_json(agent_id="agent-1"), dispatch_json(agent_id="only-one")])

        turn = await Supervisor(llm).decide(room, [])

        assert turn.attempts == 2
        assert turn.decision.agent_id == "only-one"
