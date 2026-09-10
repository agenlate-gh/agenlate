"""Usage recording and the Phase 2 margin."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from agenlate.billing import (
    DEFAULT_MARGIN,
    MARGIN_MAX,
    MARGIN_MIN,
    MarginError,
    UsageContext,
    UsageSummary,
    apply_margin,
    margin_amount,
    to_event,
)
from agenlate.llm import Usage

CONTEXT = UsageContext(
    user_id="user-1",
    model="anthropic/claude-sonnet-4.5",
    room_id="room-1",
    message_id="msg-1",
    generation_id="gen-1",
)


class TestRecordingPricedRequests:
    def test_provider_figures_are_stored_untouched(self) -> None:
        usage = Usage.for_call(
            prompt_tokens=1200, completion_tokens=300, cost_usd=0.004521,
            server_tool_calls=2,
        )

        event = to_event(usage, CONTEXT)

        assert event.prompt_tokens == 1200
        assert event.completion_tokens == 300
        assert event.cost_usd == pytest.approx(0.004521)
        assert event.server_tool_calls == 2
        assert event.is_priced is True

    def test_the_row_carries_its_context(self) -> None:
        event = to_event(Usage.for_call(cost_usd=0.01), CONTEXT)

        assert event.user_id == "user-1"
        assert event.room_id == "room-1"
        assert event.message_id == "msg-1"
        assert event.provider_generation_id == "gen-1"
        assert event.model == "anthropic/claude-sonnet-4.5"

    def test_a_missing_model_name_is_marked_not_blank(self) -> None:
        """The column is NOT NULL, and an empty string would be a silent gap in
        the ledger rather than a visible one."""
        event = to_event(Usage.for_call(cost_usd=0.01), UsageContext(user_id="u", model=""))

        assert event.model == "unknown"

    def test_no_margin_is_applied_when_recording(self) -> None:
        """The stored figure is what the provider charged. Marking it up in
        place would destroy the only record of the real cost."""
        usage = Usage.for_call(cost_usd=0.010)

        event = to_event(usage, CONTEXT)

        assert event.cost_usd == pytest.approx(0.010)


class TestRecordingUnpricedRequests:
    def test_an_unpriced_request_is_null_never_zero(self) -> None:
        """Zero claims the request was free. Null says nobody told us."""
        event = to_event(Usage.for_call(cost_usd=None), CONTEXT)

        assert event.cost_usd is None
        assert event.is_priced is False

    def test_a_genuinely_free_request_is_priced(self) -> None:
        event = to_event(Usage.for_call(cost_usd=0.0), CONTEXT)

        assert event.cost_usd == 0.0
        assert event.is_priced is True

    def test_tokens_are_still_recorded_when_cost_is_not(self) -> None:
        """Losing the token counts as well would leave nothing to reconcile
        against the provider's own records later."""
        usage = Usage.for_call(prompt_tokens=900, completion_tokens=100, cost_usd=None)

        event = to_event(usage, CONTEXT)

        assert event.prompt_tokens == 900
        assert event.completion_tokens == 100

    async def test_an_unpriced_request_is_warned_about(self, caplog) -> None:
        """A provider that stops reporting cost disables the spend cap, so it
        should be visible in the logs before the run guard stops the run."""
        from agenlate.billing import recorder

        class FakeClient:
            def table(self, _name):
                return self

            def insert(self, payload):
                self._payload = payload
                return self

            def select(self, *_):
                return self

            async def execute(self):
                class Response:
                    data = [
                        {
                            "id": "e1",
                            "user_id": "user-1",
                            "model": "m",
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "cost_usd": None,
                            "is_priced": False,
                            "server_tool_calls": 0,
                            "created_at": "2026-09-10T12:00:00+00:00",
                        }
                    ]

                return Response()

        with caplog.at_level(logging.WARNING):
            await recorder.record(FakeClient(), Usage.for_call(cost_usd=None), CONTEXT)

        assert any("unpriced" in record.message for record in caplog.records)


class TestMargin:
    def test_applies_the_multiplier_to_reported_cost(self) -> None:
        assert apply_margin(0.010, 1.20) == pytest.approx(0.012)

    def test_the_revenue_portion_is_the_difference(self) -> None:
        assert margin_amount(0.010, 1.20) == pytest.approx(0.002)

    def test_the_default_sits_inside_the_agreed_range(self) -> None:
        assert MARGIN_MIN <= DEFAULT_MARGIN <= MARGIN_MAX

    @pytest.mark.parametrize("multiplier", [1.0, 1.05, 1.25, 2.0, 0.9])
    def test_a_multiplier_outside_the_range_is_refused(self, multiplier) -> None:
        """The range is a commercial commitment, not a tuning knob."""
        with pytest.raises(MarginError):
            apply_margin(0.01, multiplier)

    def test_an_unpriced_request_has_no_price(self) -> None:
        """Returning zero would give the request away; inventing a figure would
        charge for a guess. The caller has to decide."""
        assert apply_margin(None) is None
        assert margin_amount(None) is None

    def test_a_free_request_stays_free(self) -> None:
        assert apply_margin(0.0) == 0.0

    def test_negative_cost_is_refused(self) -> None:
        with pytest.raises(MarginError):
            apply_margin(-0.01)

    def test_it_is_pure(self) -> None:
        """Billing arithmetic that cannot be reproduced from its inputs is
        billing arithmetic nobody can audit."""
        assert apply_margin(0.01) == apply_margin(0.01) == apply_margin(0.01)


class TestMarginIsNotWiredIn:
    """Billing is deferred to Phase 2. The margin exists so the ledger's unit
    of account is right from the first row, not so it can be used yet.
    """

    def test_nothing_outside_the_billing_package_calls_it(self) -> None:
        source_root = Path(__file__).resolve().parents[1] / "src" / "agenlate"
        offenders = []

        for path in source_root.rglob("*.py"):
            if path.parent.name == "billing":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(
                        node.func, "attr", None
                    )
                    if name in {"apply_margin", "margin_amount"}:
                        offenders.append(f"{path.name}:{node.lineno}")

        assert offenders == [], f"margin applied in MVP code paths: {offenders}"

    def test_the_recorder_does_not_import_it(self) -> None:
        from agenlate.billing import recorder

        source = Path(recorder.__file__).read_text(encoding="utf-8")

        assert "apply_margin" not in source


class TestUsageSummary:
    def test_an_empty_summary_reports_full_coverage(self) -> None:
        """No requests means nothing unknown, not zero confidence."""
        assert UsageSummary().coverage == 1.0
        assert UsageSummary().has_unpriced is False

    def test_coverage_reflects_how_much_cost_is_known(self) -> None:
        summary = UsageSummary(total_requests=10, priced_requests=8, unpriced_requests=2)

        assert summary.coverage == pytest.approx(0.8)
        assert summary.has_unpriced is True

    def test_full_coverage_when_everything_is_priced(self) -> None:
        summary = UsageSummary(total_requests=5, priced_requests=5)

        assert summary.coverage == 1.0
        assert summary.has_unpriced is False

    def test_cost_is_a_floor_when_coverage_is_partial(self) -> None:
        """Worth knowing before anyone quotes the figure as revenue."""
        summary = UsageSummary(
            total_requests=10, priced_requests=6, unpriced_requests=4, cost_usd=0.50
        )

        assert summary.coverage < 1.0
        assert summary.cost_usd == pytest.approx(0.50)
