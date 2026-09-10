"""Termination guarantees.

Each limit is driven independently to its own reason, because a guard that
stops runs for the wrong stated reason is barely better than one that does not
stop them.
"""

from __future__ import annotations

import pytest

from agenlate.llm import Usage
from agenlate.supervisor.contract import SupervisorDecision
from agenlate.supervisor.limits import (
    RunGuard,
    RunLimits,
    TerminationReason,
)


def dispatch(agent_id: str = "a1", instruction: str = "do the thing") -> SupervisorDecision:
    return SupervisorDecision(
        reasoning="next step",
        action="dispatch",
        objective_status="in_progress",
        agent_id=agent_id,
        instruction=instruction,
    )


def complete() -> SupervisorDecision:
    return SupervisorDecision(
        reasoning="done",
        action="complete",
        objective_status="achieved",
        message_to_user="finished",
    )


def priced(cost: float) -> Usage:
    return Usage.for_call(prompt_tokens=100, completion_tokens=20, cost_usd=cost)


def unpriced() -> Usage:
    return Usage.for_call(prompt_tokens=100, completion_tokens=20, cost_usd=None)


class TestFreshRun:
    def test_a_new_guard_permits_work(self) -> None:
        assert RunGuard().check() is None

    def test_normal_progress_does_not_trip_anything(self) -> None:
        guard = RunGuard()

        for i in range(5):
            guard.record_usage(priced(0.001))
            guard.record_dispatch(dispatch(instruction=f"step {i}"))
            guard.record_progress(new_messages=2)
            assert guard.check() is None


class TestMaxTurns:
    def test_stops_at_the_turn_limit(self) -> None:
        guard = RunGuard(RunLimits(max_turns=3))

        for i in range(3):
            assert guard.check() is None
            guard.record_dispatch(dispatch(instruction=f"step {i}"))
            guard.record_progress(new_messages=1)

        assert guard.check() is TerminationReason.MAX_TURNS

    def test_counts_dispatches_not_calls(self) -> None:
        guard = RunGuard(RunLimits(max_turns=2))
        guard.record_usage(priced(0.0001))
        guard.record_usage(priced(0.0001))
        guard.record_usage(priced(0.0001))

        assert guard.check() is None

    def test_remaining_turns_is_reported(self) -> None:
        guard = RunGuard(RunLimits(max_turns=5))
        guard.record_dispatch(dispatch())

        assert guard.remaining_turns == 4


class TestSpendCap:
    def test_stops_at_the_cap(self) -> None:
        guard = RunGuard(RunLimits(spend_cap_usd=0.10))

        guard.record_usage(priced(0.04))
        assert guard.check() is None
        guard.record_usage(priced(0.05))
        assert guard.check() is None
        guard.record_usage(priced(0.02))

        assert guard.check() is TerminationReason.SPEND_CAP

    def test_reaching_the_cap_exactly_stops(self) -> None:
        guard = RunGuard(RunLimits(spend_cap_usd=0.10))
        guard.record_usage(priced(0.10))

        assert guard.check() is TerminationReason.SPEND_CAP

    def test_repair_and_failed_calls_count_toward_the_cap(self) -> None:
        """They were paid for, so excluding them would let a run overspend by
        exactly the amount it wasted."""
        guard = RunGuard(RunLimits(spend_cap_usd=0.05))

        wasted_repairs = priced(0.02) + priced(0.02) + priced(0.02)
        guard.record_usage(wasted_repairs)

        assert guard.check() is TerminationReason.SPEND_CAP

    def test_remaining_budget_is_reported(self) -> None:
        guard = RunGuard(RunLimits(spend_cap_usd=1.00))
        guard.record_usage(priced(0.25))

        assert guard.remaining_budget_usd == pytest.approx(0.75)

    def test_remaining_budget_never_goes_negative(self) -> None:
        guard = RunGuard(RunLimits(spend_cap_usd=0.10))
        guard.record_usage(priced(5.00))

        assert guard.remaining_budget_usd == 0.0


class TestStallDetection:
    def test_stops_when_one_instruction_repeats(self) -> None:
        guard = RunGuard(RunLimits(stall_repeat_limit=3))

        for _ in range(3):
            guard.record_dispatch(dispatch(instruction="research coffee"))
            guard.record_progress(new_messages=1)

        assert guard.check() is TerminationReason.STALLED

    def test_light_rephrasing_still_counts_as_a_repeat(self) -> None:
        """A Supervisor going in circles rarely repeats itself word for word."""
        guard = RunGuard(RunLimits(stall_repeat_limit=3))

        guard.record_dispatch(dispatch(instruction="Research coffee trends"))
        guard.record_dispatch(dispatch(instruction="research   coffee trends"))
        guard.record_dispatch(dispatch(instruction="Research coffee trends."))

        assert guard.check() is TerminationReason.STALLED

    def test_an_alternating_loop_is_caught(self) -> None:
        """A, B, A, B, A is a loop too. Counting occurrences rather than
        consecutive repeats catches it."""
        guard = RunGuard(RunLimits(stall_repeat_limit=3))

        for instruction in ["step a", "step b", "step a", "step b", "step a"]:
            guard.record_dispatch(dispatch(instruction=instruction))
            guard.record_progress(new_messages=1)

        assert guard.check() is TerminationReason.STALLED

    def test_the_same_instruction_to_different_agents_is_not_a_stall(self) -> None:
        """Asking two specialists to review the same draft is real work."""
        guard = RunGuard(RunLimits(stall_repeat_limit=3))

        for agent_id in ("a1", "a2", "a3"):
            guard.record_dispatch(dispatch(agent_id=agent_id, instruction="review the draft"))
            guard.record_progress(new_messages=1)

        assert guard.check() is None

    def test_genuine_progress_never_stalls(self) -> None:
        guard = RunGuard(RunLimits(stall_repeat_limit=3, max_turns=100))

        for i in range(20):
            guard.record_dispatch(dispatch(instruction=f"step {i}"))
            guard.record_progress(new_messages=1)

        assert guard.check() is None

    def test_terminal_decisions_do_not_register_a_signature(self) -> None:
        guard = RunGuard(RunLimits(stall_repeat_limit=2))

        guard.record_dispatch(complete())
        guard.record_dispatch(complete())

        assert guard.check() is None


class TestNoProgress:
    def test_stops_after_consecutive_barren_turns(self) -> None:
        guard = RunGuard(RunLimits(no_progress_limit=3))

        for i in range(3):
            guard.record_dispatch(dispatch(instruction=f"step {i}"))
            guard.record_progress(new_messages=0)

        assert guard.check() is TerminationReason.NO_PROGRESS

    def test_the_counter_resets_on_output(self) -> None:
        """Only a sustained silence means something is wrong; one empty reply
        is noise."""
        guard = RunGuard(RunLimits(no_progress_limit=3))

        guard.record_progress(new_messages=0)
        guard.record_progress(new_messages=0)
        guard.record_progress(new_messages=1)
        guard.record_progress(new_messages=0)

        assert guard.check() is None

    def test_non_consecutive_barren_turns_do_not_accumulate(self) -> None:
        guard = RunGuard(RunLimits(no_progress_limit=2, max_turns=100))

        for _ in range(10):
            guard.record_progress(new_messages=0)
            guard.record_progress(new_messages=3)

        assert guard.check() is None


class TestUnpricedCeiling:
    def test_stops_when_cost_stops_being_reported(self) -> None:
        """With no reported cost the spend cap protects nobody, so continuing
        would spend the user's money with no way to measure it."""
        guard = RunGuard(RunLimits(unpriced_call_limit=3))

        for _ in range(3):
            guard.record_usage(unpriced())

        assert guard.check() is TerminationReason.UNPRICED_CEILING

    def test_priced_calls_do_not_count_toward_it(self) -> None:
        guard = RunGuard(RunLimits(unpriced_call_limit=3, spend_cap_usd=100))

        for _ in range(20):
            guard.record_usage(priced(0.001))

        assert guard.check() is None

    def test_a_few_unpriced_calls_are_tolerated(self) -> None:
        guard = RunGuard(RunLimits(unpriced_call_limit=5))

        guard.record_usage(unpriced())
        guard.record_usage(priced(0.001))
        guard.record_usage(unpriced())

        assert guard.check() is None


class TestReasonPrecedence:
    def test_stalling_is_reported_ahead_of_the_turn_limit(self) -> None:
        """A stalled run has usually burned turns too. Telling the user the
        same step kept repeating is more actionable than naming the backstop
        it happened to hit."""
        guard = RunGuard(RunLimits(max_turns=3, stall_repeat_limit=3))

        for _ in range(3):
            guard.record_dispatch(dispatch(instruction="the same thing"))
            guard.record_progress(new_messages=1)

        assert guard.check() is TerminationReason.STALLED

    def test_the_turn_limit_is_the_backstop(self) -> None:
        guard = RunGuard(RunLimits(max_turns=3, stall_repeat_limit=99))

        for i in range(3):
            guard.record_dispatch(dispatch(instruction=f"step {i}"))
            guard.record_progress(new_messages=1)

        assert guard.check() is TerminationReason.MAX_TURNS


class TestReasonsAreUsable:
    def test_every_reason_has_a_description(self) -> None:
        for reason in TerminationReason:
            assert reason.describe()

    def test_no_description_leaks_an_internal_name(self) -> None:
        """These are shown to non-technical users."""
        for reason in TerminationReason:
            assert "_" not in reason.describe()

    def test_only_completion_counts_as_success(self) -> None:
        assert TerminationReason.COMPLETED.is_success
        for reason in TerminationReason:
            if reason is not TerminationReason.COMPLETED:
                assert not reason.is_success

    def test_limits_are_distinguished_from_outcomes(self) -> None:
        assert TerminationReason.SPEND_CAP.is_limit
        assert TerminationReason.STALLED.is_limit
        assert not TerminationReason.COMPLETED.is_limit
        assert not TerminationReason.AWAITING_USER.is_limit
        assert not TerminationReason.CANCELLED.is_limit

    def test_every_limit_the_guard_can_return_is_marked_as_one(self) -> None:
        guard_reasons = {
            TerminationReason.MAX_TURNS,
            TerminationReason.SPEND_CAP,
            TerminationReason.STALLED,
            TerminationReason.NO_PROGRESS,
            TerminationReason.UNPRICED_CEILING,
        }

        for reason in guard_reasons:
            assert reason.is_limit


class TestStateReporting:
    def test_tracks_spending_and_turns(self) -> None:
        guard = RunGuard()
        guard.record_usage(priced(0.03))
        guard.record_dispatch(dispatch())

        assert guard.state.cost_spent == pytest.approx(0.03)
        assert guard.state.turns == 1
        assert guard.state.unpriced_calls == 0

    def test_mixed_pricing_keeps_both_figures(self) -> None:
        guard = RunGuard()
        guard.record_usage(priced(0.02))
        guard.record_usage(unpriced())

        assert guard.state.cost_spent == pytest.approx(0.02)
        assert guard.state.unpriced_calls == 1
        assert guard.state.usage.has_unknown_cost is True
