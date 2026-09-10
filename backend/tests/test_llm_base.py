"""The provider seam: usage arithmetic and the protocol contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agenlate.llm import FakeLLM, LLMClient, LLMResponse, Usage


class TestUsageArithmetic:
    def test_totals_tokens(self) -> None:
        usage = Usage.for_call(prompt_tokens=1000, completion_tokens=250, cost_usd=0.01)

        assert usage.total_tokens == 1250

    def test_addition_sums_tokens_costs_and_calls(self) -> None:
        first = Usage.for_call(prompt_tokens=100, completion_tokens=20, cost_usd=0.001)
        second = Usage.for_call(prompt_tokens=200, completion_tokens=40, cost_usd=0.002)

        total = first + second

        assert total.prompt_tokens == 300
        assert total.completion_tokens == 60
        assert total.cost_usd == pytest.approx(0.003)
        assert total.calls == 2

    def test_empty_usage_is_an_identity(self) -> None:
        """Accumulators start empty and must not count as a call."""
        call = Usage.for_call(prompt_tokens=10, completion_tokens=5, cost_usd=0.5)

        total = Usage() + call

        assert total == call
        assert Usage().calls == 0


class TestUnknownCost:
    def test_reported_cost_is_priced(self) -> None:
        usage = Usage.for_call(cost_usd=0.01)

        assert usage.has_unknown_cost is False
        assert usage.unpriced_calls == 0

    def test_missing_cost_is_counted_not_zeroed(self) -> None:
        usage = Usage.for_call(cost_usd=None)

        assert usage.cost_usd is None
        assert usage.has_unknown_cost is True
        assert usage.unpriced_calls == 1

    def test_zero_is_priced_and_distinct_from_missing(self) -> None:
        """Free models report zero. Reporting nothing is a different claim."""
        free = Usage.for_call(cost_usd=0.0)

        assert free.has_unknown_cost is False
        assert free.cost_usd == 0.0

    def test_mixing_known_and_unknown_keeps_both_facts(self) -> None:
        """A total must not lose what we know, nor pretend to know what we
        don't. The known portion sums; the gap is counted separately."""
        known = Usage.for_call(prompt_tokens=100, cost_usd=0.05)
        unknown = Usage.for_call(prompt_tokens=100, cost_usd=None)

        total = known + unknown

        assert total.cost_usd == pytest.approx(0.05)
        assert total.unpriced_calls == 1
        assert total.calls == 2
        assert total.has_unknown_cost is True

    def test_all_unknown_stays_none_rather_than_zero(self) -> None:
        total = Usage.for_call(cost_usd=None) + Usage.for_call(cost_usd=None)

        assert total.cost_usd is None
        assert total.unpriced_calls == 2

    def test_known_cost_names_the_assumption(self) -> None:
        """known_cost_usd is the only way to get a float out of an unknown, so
        treating it as zero has to be written down."""
        unknown = Usage.for_call(cost_usd=None)

        assert unknown.known_cost_usd == 0.0
        assert unknown.cost_usd is None

    def test_negative_cost_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Usage(cost_usd=-0.01)


class TestProtocolConformance:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeLLM([]), LLMClient)

    def test_a_class_missing_complete_does_not(self) -> None:
        class NotAClient:
            pass

        assert not isinstance(NotAClient(), LLMClient)


class TestLLMResponse:
    def test_plain_completion_wants_no_tools(self) -> None:
        assert LLMResponse(content="hello").wants_tools is False

    def test_response_with_tool_calls_wants_tools(self) -> None:
        response = LLMResponse(content="", tool_calls=[{"id": "1", "name": "search"}])

        assert response.wants_tools is True
