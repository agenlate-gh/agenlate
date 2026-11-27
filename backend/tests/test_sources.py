"""Links an agent did not get from a search or from what it was given.

A model asked for sources sometimes writes plausible addresses from memory.
These tests pin down that such links are sent back once for a real search,
and taken out if they survive, while links that are backed stay untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from agenlate.agents.executor import execute_agent
from agenlate.agents.sources import (
    REMOVED_MARKER,
    find_links,
    normalize,
    remove_links,
    unsupported_links,
)
from agenlate.agents.tools import DATETIME
from agenlate.llm import FakeLLM, LLMResponse, Usage
from agenlate.llm.openrouter import ENDPOINT, OpenRouterClient
from agenlate.models import Agent, Emitter, Message

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
REAL = "https://caracasquierecafe.com/5ta-edicion"
INVENTED = "https://www.instagram.com/p/CXyZ1234567/"


def make_agent(enabled_tools: list[str] | None = None) -> Agent:
    return Agent(
        id="agent-1",
        creator_id="u1",
        name="Researcher",
        role="finds current information",
        system_prompt="You are a researcher.",
        enabled_tools=enabled_tools,
        created_at=NOW,
        updated_at=NOW,
    )


def message(content: str) -> Message:
    return Message(
        id="m1",
        seq=1,
        room_id="r1",
        emitter=Emitter.AGENT,
        emitter_name="Researcher",
        content=content,
        created_at=NOW,
    )


def reply(content: str, citations: list[str] | None = None, cost: float = 0.001) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=Usage.for_call(prompt_tokens=100, completion_tokens=50, cost_usd=cost),
        model="fake/model",
        citations=citations or [],
    )


async def run(llm: FakeLLM, *, agent: Agent | None = None, history: list[Message] | None = None, instruction: str = "Find two cafés."):
    return await execute_agent(
        agent or make_agent(),
        instruction=instruction,
        objective="Brief on cafés in Caracas.",
        transcript=history or [],
        llm=llm,
    )


class TestFindingAndMatching:
    def test_trailing_punctuation_is_not_part_of_a_link(self) -> None:
        assert find_links(f"See {REAL}. Also ({INVENTED}).") == [REAL, INVENTED]

    def test_trivial_differences_are_the_same_address(self) -> None:
        assert normalize("https://www.Example.com/a/") == normalize("http://example.com/a#top")

    def test_an_invented_path_on_a_real_site_is_a_different_address(self) -> None:
        assert normalize("https://elpitazo.net/") != normalize("https://elpitazo.net/made-up-article")

    def test_only_unbacked_links_are_reported_once_each(self) -> None:
        text = f"[a]({REAL}) and {INVENTED} and again {INVENTED}"
        assert unsupported_links(text, [REAL]) == [INVENTED]


class TestRemoving:
    def test_a_markdown_link_keeps_its_text(self) -> None:
        assert remove_links(f"Read [the report]({INVENTED}).", [INVENTED]) == "Read the report."

    def test_a_bare_link_is_replaced_with_a_marker(self) -> None:
        assert remove_links(f"Source: {INVENTED}.", [INVENTED]) == f"Source: {REMOVED_MARKER}."

    def test_other_links_are_left_alone(self) -> None:
        text = f"{REAL} and {INVENTED}"
        assert remove_links(text, [INVENTED]) == f"{REAL} and {REMOVED_MARKER}"


class TestAgentTurn:
    async def test_a_link_from_the_search_is_kept_in_one_call(self) -> None:
        llm = FakeLLM([reply(f"Caracas Quiere Café: {REAL}", citations=[REAL])])
        result = await run(llm)

        assert llm.call_count == 1
        assert REAL in result.content
        assert result.removed_links == 0

    async def test_a_link_from_the_transcript_is_kept(self) -> None:
        llm = FakeLLM([reply(f"As found earlier: {REAL}")])
        result = await run(llm, history=[message(f"Source: {REAL}")])

        assert llm.call_count == 1
        assert result.removed_links == 0

    async def test_a_link_in_the_instruction_is_kept(self) -> None:
        llm = FakeLLM([reply(f"Summary of {REAL}")])
        result = await run(llm, instruction=f"Read {REAL} and summarise it.")

        assert llm.call_count == 1
        assert result.removed_links == 0

    async def test_an_invented_link_is_sent_back_for_a_search(self) -> None:
        llm = FakeLLM([
            reply(f"Café X: {INVENTED}", cost=0.001),
            reply(f"Caracas Quiere Café: {REAL}", citations=[REAL], cost=0.007),
        ])
        result = await run(llm)

        assert llm.call_count == 2
        correction = llm.calls[1]["messages"][-1]["content"]
        assert INVENTED in correction and "Search the web" in correction
        assert result.content == f"Caracas Quiere Café: {REAL}"
        assert result.removed_links == 0
        # The second call is paid for, so it is counted.
        assert result.usage.cost_usd == pytest.approx(0.008)
        assert result.usage.calls == 2

    async def test_a_link_still_invented_after_the_retry_is_removed(self) -> None:
        llm = FakeLLM([reply(f"Source: {INVENTED}"), reply(f"Source: {INVENTED}")])
        result = await run(llm)

        assert llm.call_count == 2
        assert INVENTED not in result.content
        assert REMOVED_MARKER in result.content
        assert "1 link was removed" in result.content
        assert result.removed_links == 1

    async def test_without_search_there_is_no_retry_only_removal(self) -> None:
        llm = FakeLLM([reply(f"Source: {INVENTED}")])
        result = await run(llm, agent=make_agent(enabled_tools=[DATETIME]))

        assert llm.call_count == 1
        assert INVENTED not in result.content
        assert result.removed_links == 1

    async def test_a_reply_without_links_is_untouched(self) -> None:
        llm = FakeLLM([reply("Two cafés, no links needed.")])
        result = await run(llm)

        assert llm.call_count == 1
        assert result.content == "Two cafés, no links needed."


class TestReadingCitations:
    @respx.mock
    async def test_search_results_are_read_from_the_annotations(self) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(200, json={
                "id": "gen-1",
                "model": "qwen/qwen3.7-flash",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Answer",
                        "annotations": [
                            {"type": "url_citation", "url_citation": {"url": REAL, "title": "t"}},
                            {"type": "something_else"},
                            {"type": "url_citation", "url_citation": {}},
                        ],
                    },
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.001},
            })
        )
        async with httpx.AsyncClient() as http:
            client = OpenRouterClient("sk-or-v1-" + "a" * 64, http_client=http)
            response = await client.complete(system="s", messages=[{"role": "user", "content": "q"}])

        assert response.citations == [REAL]
