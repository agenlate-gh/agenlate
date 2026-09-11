"""Agent execution and OpenRouter server tools.

The tool loop runs on OpenRouter's infrastructure, not ours: one request goes
out and a finished answer comes back. These tests pin down what we send, what
we record, and that we do not reintroduce a client-side loop.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agenlate.agents.executor import AgentResult, execute_agent
from agenlate.agents.tools import (
    DATETIME,
    DEFAULT_TOOLS,
    MAX_TOOL_CALLS,
    UNSUPPORTED_ON_CHAT_COMPLETIONS,
    WEB_FETCH,
    WEB_SEARCH,
    build_tool_payload,
    resolve_tools,
)
from agenlate.llm import FakeLLM, LLMError, LLMResponse, Usage
from agenlate.models import Agent, Emitter, Message

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def make_agent(enabled_tools: list[str] | None = None) -> Agent:
    return Agent(
        id="agent-1",
        creator_id="u1",
        name="Researcher",
        role="finds and verifies current information",
        system_prompt="You are a meticulous researcher.",
        enabled_tools=enabled_tools,
        created_at=NOW,
        updated_at=NOW,
    )


def transcript() -> list[Message]:
    return [
        Message(
            id="m1",
            seq=1,
            room_id="r1",
            emitter=Emitter.SUPERVISOR,
            emitter_name="Supervisor",
            content="Research is needed first.",
            created_at=NOW,
        )
    ]


async def run(llm: FakeLLM, agent: Agent | None = None, **kwargs) -> AgentResult:
    return await execute_agent(
        agent or make_agent(),
        "Find three sources on coffee trends",
        "Write a post about coffee trends",
        transcript(),
        llm,
        **kwargs,
    )


class TestToolSelection:
    def test_none_means_the_defaults(self) -> None:
        """An agent created without thinking about tools should still be
        capable; opting out is the deliberate act."""
        assert resolve_tools(None) == list(DEFAULT_TOOLS)

    def test_an_empty_list_means_no_tools(self) -> None:
        """Distinct from None. A user who switched everything off gets that."""
        assert resolve_tools([]) == []
        assert build_tool_payload([]) is None

    def test_a_subset_is_honoured(self) -> None:
        assert resolve_tools([WEB_SEARCH]) == [WEB_SEARCH]

    def test_unknown_tools_are_dropped(self) -> None:
        """A stale or mistyped identifier would make the whole request fail,
        taking the agent's turn with it."""
        assert resolve_tools([WEB_SEARCH, "openrouter:not_a_real_tool"]) == [WEB_SEARCH]

    def test_the_payload_uses_the_type_field(self) -> None:
        payload = build_tool_payload([WEB_SEARCH, WEB_FETCH])

        assert payload == [{"type": WEB_SEARCH}, {"type": WEB_FETCH}]

    def test_defaults_cover_research(self) -> None:
        assert WEB_SEARCH in DEFAULT_TOOLS
        assert WEB_FETCH in DEFAULT_TOOLS
        assert DATETIME in DEFAULT_TOOLS

    def test_tools_this_endpoint_rejects_are_dropped(self) -> None:
        """chat-completions answers 400 for shell, bash, apply_patch and
        tool_search. One of them anywhere in a request fails the whole call and
        loses the agent's turn, so they never reach the wire."""
        for tool in UNSUPPORTED_ON_CHAT_COMPLETIONS:
            assert resolve_tools([WEB_SEARCH, tool]) == [WEB_SEARCH]

    def test_no_default_is_a_tool_this_endpoint_rejects(self) -> None:
        assert not set(DEFAULT_TOOLS) & UNSUPPORTED_ON_CHAT_COMPLETIONS


class TestRequestShape:
    async def test_tools_are_sent(self) -> None:
        llm = FakeLLM(["Found three sources."])

        await run(llm)

        assert llm.last_call["tools"] == [{"type": t} for t in DEFAULT_TOOLS]

    async def test_the_step_budget_is_sent_with_them(self) -> None:
        llm = FakeLLM(["Found three sources."])

        await run(llm)

        assert llm.last_call["max_tool_calls"] == MAX_TOOL_CALLS

    async def test_an_agent_with_no_tools_sends_neither(self) -> None:
        """Sending a budget with no tools would be meaningless."""
        llm = FakeLLM(["Answered from memory."])

        await run(llm, make_agent(enabled_tools=[]))

        assert llm.last_call["tools"] is None
        assert llm.last_call["max_tool_calls"] is None

    async def test_the_budget_is_configurable(self) -> None:
        llm = FakeLLM(["done"])

        await run(llm, max_tool_calls=3)

        assert llm.last_call["max_tool_calls"] == 3

    async def test_the_agent_persona_leads_the_system_prompt(self) -> None:
        llm = FakeLLM(["done"])

        await run(llm)

        assert llm.last_call["system"].startswith("You are a meticulous researcher.")

    async def test_the_objective_and_instruction_both_reach_the_model(self) -> None:
        llm = FakeLLM(["done"])

        await run(llm)

        assert "Write a post about coffee trends" in llm.last_call["system"]
        assert "Find three sources" in llm.last_call["messages"][0]["content"]

    async def test_the_transcript_is_included(self) -> None:
        llm = FakeLLM(["done"])

        await run(llm)

        assert "Research is needed first." in llm.last_call["messages"][0]["content"]

    async def test_agents_run_warmer_than_the_supervisor(self) -> None:
        """Agents do the creative work; turn-taking is a decision."""
        llm = FakeLLM(["done"])

        await run(llm)

        assert llm.last_call["temperature"] > 0


class TestSingleRequest:
    async def test_a_direct_answer_takes_one_call(self) -> None:
        llm = FakeLLM(["Answered without tools."])

        result = await run(llm)

        assert result.content == "Answered without tools."
        assert llm.call_count == 1

    async def test_a_tool_using_answer_also_takes_one_call(self) -> None:
        """OpenRouter runs the tool loop server-side and returns a finished
        answer. A client-side loop here would be a second orchestrator."""
        llm = FakeLLM(
            [
                LLMResponse(
                    content="I searched and found three sources.",
                    usage=Usage.for_call(
                        prompt_tokens=2000, completion_tokens=400,
                        cost_usd=0.02, server_tool_calls=3,
                    ),
                    model="anthropic/claude-sonnet-4.5",
                )
            ]
        )

        result = await run(llm)

        assert llm.call_count == 1
        assert result.tool_rounds == 3
        llm.assert_exhausted()

    async def test_many_tool_steps_still_take_one_call(self) -> None:
        llm = FakeLLM(
            [
                LLMResponse(
                    content="Done after a lot of searching.",
                    usage=Usage.for_call(cost_usd=0.05, server_tool_calls=8),
                )
            ]
        )

        result = await run(llm)

        assert llm.call_count == 1
        assert result.tool_rounds == 8


class TestUsageAccounting:
    async def test_tool_steps_are_recorded_alongside_cost(self) -> None:
        """Web search is priced per result rather than per token, and whether
        that is already inside the reported cost is undocumented. Keeping the
        count lets the question be settled from real data."""
        llm = FakeLLM(
            [
                LLMResponse(
                    content="done",
                    usage=Usage.for_call(cost_usd=0.02, server_tool_calls=4),
                )
            ]
        )

        result = await run(llm)

        assert result.usage.cost_usd == pytest.approx(0.02)
        assert result.usage.server_tool_calls == 4

    async def test_tool_counts_accumulate_across_turns(self) -> None:
        first = Usage.for_call(cost_usd=0.01, server_tool_calls=2)
        second = Usage.for_call(cost_usd=0.01, server_tool_calls=3)

        assert (first + second).server_tool_calls == 5

    async def test_a_toolless_turn_reports_no_tool_steps(self) -> None:
        llm = FakeLLM(["done"])

        result = await run(llm)

        assert result.usage.server_tool_calls == 0

    async def test_the_model_is_recorded(self) -> None:
        llm = FakeLLM(["done"], model="anthropic/claude-sonnet-4.5")

        result = await run(llm)

        assert result.model == "anthropic/claude-sonnet-4.5"


class TestOutcomes:
    async def test_whitespace_only_output_counts_as_empty(self) -> None:
        result = await run(FakeLLM(["   \n  "]))

        assert result.is_empty is True
        assert result.content == ""

    async def test_real_output_is_not_empty(self) -> None:
        result = await run(FakeLLM(["Something useful."]))

        assert result.is_empty is False

    async def test_an_empty_turn_still_reports_its_cost(self) -> None:
        """The call succeeded and was paid for; it simply moved nothing."""
        llm = FakeLLM([""], usage_per_call=Usage.for_call(cost_usd=0.003))

        result = await run(llm)

        assert result.is_empty is True
        assert result.usage.cost_usd == pytest.approx(0.003)

    async def test_provider_failures_propagate(self) -> None:
        """The orchestrator decides what a failed turn means for the run;
        swallowing it here would hide a dead key behind an empty answer."""
        llm = FakeLLM([LLMError("OpenRouter returned 402")])

        with pytest.raises(LLMError, match="402"):
            await run(llm)


class TestOpenRouterPayload:
    """The tool fields as they actually go over the wire."""

    @staticmethod
    async def send(agent_tools: list[str] | None):
        import httpx
        import respx

        from agenlate.llm.openrouter import ENDPOINT, OpenRouterClient

        with respx.mock:
            route = respx.post(ENDPOINT).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "id": "gen-1",
                        "model": "m",
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "cost": 0.01,
                            "server_tool_use": {"web_search_requests": 2, "shell_calls": 1},
                        },
                    },
                )
            )
            client = OpenRouterClient("sk-or-v1-test")
            result = await execute_agent(
                make_agent(agent_tools),
                "instruction",
                "objective",
                transcript(),
                client,
            )
            import json as _json

            body = _json.loads(route.calls.last.request.read())
            await client.aclose()
            return body, result

    async def test_tools_and_budget_appear_in_the_request_body(self) -> None:
        body, _ = await self.send(None)

        assert body["tools"] == [{"type": t} for t in DEFAULT_TOOLS]
        assert body["max_tool_calls"] == MAX_TOOL_CALLS

    async def test_no_tool_fields_when_the_agent_has_none(self) -> None:
        body, _ = await self.send([])

        assert "tools" not in body
        assert "max_tool_calls" not in body

    async def test_server_tool_counts_are_summed_from_the_response(self) -> None:
        """OpenRouter reports per-tool counts. New tool names appear
        regularly, so unknown keys are counted rather than dropped."""
        _, result = await self.send(None)

        assert result.usage.server_tool_calls == 3
