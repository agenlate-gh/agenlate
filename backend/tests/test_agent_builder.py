"""The conversation that writes an agent's instructions.

This is the Natural Language Builder: someone describes the worker they want
and gets one, without ever meeting a box labelled "system prompt".
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agenlate.agents.builder import (
    NO_INSTRUCTIONS_YET,
    REPLY_MAX,
    SYSTEM_PROMPT_MAX,
    BuilderError,
    BuilderReply,
    build_messages,
    refine_agent,
)
from agenlate.llm import FakeLLM, LLMError, Usage


def wrote(instructions: str, reply: str = "Written.") -> str:
    return json.dumps(
        {"reply": reply, "instructions": instructions, "needs_answer": False}
    )


def asked(question: str) -> str:
    return json.dumps({"reply": question, "instructions": None, "needs_answer": True})


async def turn(llm, **kwargs):
    defaults = dict(
        name="Researcher",
        role="finds and verifies information",
        instructions=None,
        conversation=[{"role": "user", "content": "I need someone who checks facts"}],
    )
    return await refine_agent(llm, **{**defaults, **kwargs})


class TestContext:
    def test_the_worker_is_described_to_the_builder(self) -> None:
        _, messages = build_messages("Auditor", "reviews contracts", None, [])

        content = messages[0]["content"]
        assert "Auditor" in content
        assert "reviews contracts" in content

    def test_a_first_version_says_there_are_no_instructions_yet(self) -> None:
        _, messages = build_messages("A", "r", None, [])

        assert NO_INSTRUCTIONS_YET in messages[0]["content"]

    def test_existing_instructions_are_shown_so_they_can_be_revised(self) -> None:
        """Revising means keeping what the user did not ask to change, which is
        impossible if the current version is not visible."""
        _, messages = build_messages("A", "r", "You always cite sources.", [])

        assert "You always cite sources." in messages[0]["content"]

    def test_the_conversation_is_included_in_order(self) -> None:
        _, messages = build_messages(
            "A",
            "r",
            None,
            [
                {"role": "user", "content": "FIRST-THING"},
                {"role": "assistant", "content": "SECOND-THING"},
                {"role": "user", "content": "THIRD-THING"},
            ],
        )

        content = messages[0]["content"]
        assert content.index("FIRST-THING") < content.index("THIRD-THING")

    def test_the_builder_is_told_the_worker_joins_a_team(self) -> None:
        """Instructions written for a lone assistant produce an agent that
        addresses the user directly and ignores the coordinator."""
        system, _ = build_messages("A", "r", None, [])

        assert "coordinator" in system.lower()

    def test_the_builder_is_told_to_ask_one_thing_at_a_time(self) -> None:
        """A form disguised as a chat is worse than the form was."""
        system, _ = build_messages("A", "r", None, [])

        assert "two questions" in system.lower()


class TestWritingInstructions:
    async def test_a_clear_description_produces_instructions(self) -> None:
        llm = FakeLLM([wrote("You are a meticulous fact checker. You always cite.")])

        result = await turn(llm)

        assert result.reply.wrote_instructions
        assert "fact checker" in result.reply.instructions
        assert result.reply.needs_answer is False

    async def test_the_reply_is_what_the_user_reads(self) -> None:
        llm = FakeLLM(
            [wrote("You are a checker.", reply="I have written its instructions.")]
        )

        result = await turn(llm)

        assert result.reply.reply == "I have written its instructions."

    async def test_an_ambiguous_request_asks_rather_than_guesses(self) -> None:
        llm = FakeLLM([asked("Should it flag uncertain claims, or remove them?")])

        result = await turn(llm)

        assert result.reply.needs_answer is True
        assert result.reply.wrote_instructions is False

    async def test_json_mode_is_requested(self) -> None:
        llm = FakeLLM([wrote("x")])

        await turn(llm)

        assert llm.last_call["json_mode"] is True

    async def test_there_is_room_for_long_instructions(self) -> None:
        """The form advertises 8,000 characters; a small token budget would
        silently truncate them."""
        llm = FakeLLM([wrote("x")])

        await turn(llm)

        assert llm.last_call["max_tokens"] >= 2048


class TestContract:
    def test_instructions_may_be_absent_when_asking(self) -> None:
        reply = BuilderReply(reply="What tone?", needs_answer=True)

        assert reply.instructions is None
        assert reply.wrote_instructions is False

    def test_whitespace_instructions_do_not_count_as_written(self) -> None:
        reply = BuilderReply(reply="Done", instructions="   ")

        assert reply.wrote_instructions is False

    def test_instructions_are_capped_at_the_advertised_limit(self) -> None:
        with pytest.raises(ValidationError):
            BuilderReply(reply="Done", instructions="x" * (SYSTEM_PROMPT_MAX + 1))

    def test_the_reply_is_capped(self) -> None:
        """It is a chat message, not a second copy of the instructions."""
        with pytest.raises(ValidationError):
            BuilderReply(reply="x" * (REPLY_MAX + 1))

    def test_an_invented_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BuilderReply.model_validate({"reply": "ok", "confidence": 0.9})


class TestRecovery:
    async def test_markdown_fences_cost_no_round_trip(self) -> None:
        llm = FakeLLM([f"```json\n{wrote('You are a checker.')}\n```"])

        result = await turn(llm)

        assert result.attempts == 1
        assert result.reply.wrote_instructions

    async def test_a_malformed_reply_is_repaired_once(self) -> None:
        llm = FakeLLM(["not json at all", wrote("You are a checker.")])

        result = await turn(llm)

        assert result.attempts == 2
        llm.assert_exhausted()

    async def test_the_repair_quotes_the_problem(self) -> None:
        llm = FakeLLM(["nonsense", wrote("x")])

        await turn(llm)

        assert "not a valid reply" in llm.calls[1]["messages"][-1]["content"]

    async def test_it_gives_up_rather_than_inventing_instructions(self) -> None:
        """Writing instructions the user never asked for would put words in
        their agent's mouth."""
        llm = FakeLLM(["nonsense", "still nonsense"])

        with pytest.raises(BuilderError):
            await turn(llm)

    async def test_fewer_repairs_than_the_supervisor_gets(self) -> None:
        """A failure here is one stalled message the user can retry, not a run
        ending halfway."""
        llm = FakeLLM(["bad", "bad", wrote("x")])

        with pytest.raises(BuilderError):
            await turn(llm)

        assert llm.call_count == 2

    async def test_provider_failures_propagate(self) -> None:
        llm = FakeLLM([LLMError("OpenRouter returned 402")])

        with pytest.raises(LLMError):
            await turn(llm)


class TestAccounting:
    async def test_the_cost_is_reported(self) -> None:
        llm = FakeLLM([wrote("x")], usage_per_call=Usage.for_call(cost_usd=0.002))

        result = await turn(llm)

        assert result.usage.cost_usd == pytest.approx(0.002)

    async def test_a_repaired_turn_charges_for_both_calls(self) -> None:
        llm = FakeLLM(
            ["nonsense", wrote("x")], usage_per_call=Usage.for_call(cost_usd=0.002)
        )

        result = await turn(llm)

        assert result.usage.calls == 2
        assert result.usage.cost_usd == pytest.approx(0.004)
