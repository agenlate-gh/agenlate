"""The scripted test client.

If this is wrong, every test that depends on it is quietly wrong too.
"""

from __future__ import annotations

import pytest

from agenlate.llm import FakeLLM, LLMError, LLMResponse, ScriptExhausted, Usage


async def call(llm: FakeLLM, content: str = "hi") -> LLMResponse:
    return await llm.complete(system="s", messages=[{"role": "user", "content": content}])


class TestScriptSequencing:
    async def test_returns_responses_in_order(self) -> None:
        llm = FakeLLM(["first", "second", "third"])

        assert (await call(llm)).content == "first"
        assert (await call(llm)).content == "second"
        assert (await call(llm)).content == "third"

    async def test_running_out_names_the_problem(self) -> None:
        llm = FakeLLM(["only one"])
        await call(llm)

        with pytest.raises(ScriptExhausted, match="more calls than the test expected"):
            await call(llm)

    async def test_assert_exhausted_catches_an_under_exercised_subject(self) -> None:
        """A test that scripts four turns but whose subject stops after one
        still passes its output assertions while testing far less than it
        claims to."""
        llm = FakeLLM(["a", "b", "c", "d"])
        await call(llm)

        with pytest.raises(AssertionError, match="never used"):
            llm.assert_exhausted()

    async def test_assert_exhausted_passes_when_fully_consumed(self) -> None:
        llm = FakeLLM(["a", "b"])
        await call(llm)
        await call(llm)

        llm.assert_exhausted()


class TestScriptEntryKinds:
    async def test_a_full_response_passes_through_untouched(self) -> None:
        scripted = LLMResponse(
            content="",
            tool_calls=[{"id": "t1", "name": "openrouter:web_search"}],
            usage=Usage.for_call(prompt_tokens=7, cost_usd=0.02),
            model="specific/model",
        )
        llm = FakeLLM([scripted])

        response = await call(llm)

        assert response.wants_tools is True
        assert response.model == "specific/model"
        assert response.usage.prompt_tokens == 7

    async def test_an_exception_entry_is_raised(self) -> None:
        """Provider failure paths need exercising too, and they are the ones
        most likely to leak a key into a traceback."""
        llm = FakeLLM([LLMError("openrouter returned 402")])

        with pytest.raises(LLMError, match="402"):
            await call(llm)

    async def test_a_failure_can_sit_between_successes(self) -> None:
        llm = FakeLLM(["ok", LLMError("rate limited"), "recovered"])

        assert (await call(llm)).content == "ok"
        with pytest.raises(LLMError):
            await call(llm)
        assert (await call(llm)).content == "recovered"


class TestCallRecording:
    async def test_records_what_it_was_asked(self) -> None:
        llm = FakeLLM(["ok"])

        await llm.complete(
            system="you are the supervisor",
            messages=[{"role": "user", "content": "the objective"}],
            temperature=0.3,
            max_tokens=512,
            json_mode=True,
            tools=[{"type": "openrouter:web_search"}],
        )

        recorded = llm.last_call
        assert recorded["system"] == "you are the supervisor"
        assert recorded["json_mode"] is True
        assert recorded["temperature"] == 0.3
        assert recorded["max_tokens"] == 512
        assert recorded["tools"] == [{"type": "openrouter:web_search"}]

    async def test_counts_calls(self) -> None:
        llm = FakeLLM(["a", "b"])
        assert llm.call_count == 0

        await call(llm)
        await call(llm)

        assert llm.call_count == 2
        assert llm.remaining == 0

    def test_last_call_before_any_call_is_an_assertion(self) -> None:
        with pytest.raises(AssertionError, match="never called"):
            _ = FakeLLM(["a"]).last_call


class TestUsageAccounting:
    async def test_each_call_reports_usage(self) -> None:
        llm = FakeLLM(["a", "b"])

        first = await call(llm)
        second = await call(llm)
        total = first.usage + second.usage

        assert total.calls == 2
        assert total.total_tokens == 240

    async def test_usage_per_call_is_configurable(self) -> None:
        llm = FakeLLM(["a"], usage_per_call=Usage.for_call(cost_usd=None))

        response = await call(llm)

        assert response.usage.has_unknown_cost is True

    async def test_responses_do_not_share_a_usage_object(self) -> None:
        """Two calls returning the same mutable usage instance would make
        accumulation tests pass for the wrong reason."""
        llm = FakeLLM(["a", "b"])

        first = await call(llm)
        second = await call(llm)

        assert first.usage is not second.usage
