"""Termination guarantees.

Preventing infinite loops is the Supervisor's stated reason for existing, and
an LLM asked "are we done?" is not a guarantee — it is the thing being guarded.
So the limits here sit outside the model's judgement entirely and are counted
rather than reasoned about.

Every run ends for a named reason. "It stopped" is not an acceptable outcome:
under BYOK the money being spent is the user's, and a run that halts without
saying why leaves them unable to tell a finished job from a broken one.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from ..llm import Usage
from .contract import SupervisorDecision


class TerminationReason(str, Enum):
    """Why a run ended. Exhaustive by design."""

    COMPLETED = "completed"
    AWAITING_USER = "awaiting_user"
    MAX_TURNS = "max_turns"
    SPEND_CAP = "spend_cap"
    STALLED = "stalled"
    NO_PROGRESS = "no_progress"
    UNPRICED_CEILING = "unpriced_ceiling"
    PROVIDER_FAILURE = "provider_failure"
    SUPERVISOR_FAILURE = "supervisor_failure"
    CANCELLED = "cancelled"

    @property
    def is_success(self) -> bool:
        return self is TerminationReason.COMPLETED

    @property
    def is_limit(self) -> bool:
        """Whether a guard stopped the run rather than the work finishing."""
        return self in _LIMIT_REASONS

    def describe(self) -> str:
        """Plain language for the user.

        Shown in the interface, so it explains what happened and what to do
        rather than naming the internal condition.
        """
        return _DESCRIPTIONS[self]


_LIMIT_REASONS = frozenset(
    {
        TerminationReason.MAX_TURNS,
        TerminationReason.SPEND_CAP,
        TerminationReason.STALLED,
        TerminationReason.NO_PROGRESS,
        TerminationReason.UNPRICED_CEILING,
    }
)

_DESCRIPTIONS: dict[TerminationReason, str] = {
    TerminationReason.COMPLETED: "The objective was achieved.",
    TerminationReason.AWAITING_USER: "Your input is needed before this can continue.",
    TerminationReason.MAX_TURNS: (
        "Stopped after reaching the turn limit for this run. The work so far is "
        "kept — start a new room to continue from here."
    ),
    TerminationReason.SPEND_CAP: (
        "Stopped at the spending limit for this run, so it could not use more of "
        "your credit than you allowed."
    ),
    TerminationReason.STALLED: (
        "Stopped because the same step was being requested over and over without "
        "moving forward. Try rewording the objective, or give the agents clearer "
        "roles."
    ),
    TerminationReason.NO_PROGRESS: (
        "Stopped because the agents stopped producing any output. Their "
        "instructions may be unclear, or the model may be unavailable."
    ),
    TerminationReason.UNPRICED_CEILING: (
        "Stopped because the provider stopped reporting what requests cost, so "
        "spending could no longer be tracked."
    ),
    TerminationReason.PROVIDER_FAILURE: (
        "Stopped because the model provider returned an error. Check your "
        "OpenRouter key and credit balance."
    ),
    TerminationReason.SUPERVISOR_FAILURE: (
        "Stopped because the supervisor could not produce a usable decision. "
        "This is usually a temporary problem with the model."
    ),
    TerminationReason.CANCELLED: "You stopped this run.",
}


@dataclass(frozen=True)
class RunLimits:
    """The ceilings a single run may not cross."""

    max_turns: int = 25
    """Hard cap on dispatches. The backstop when every other check passes."""

    spend_cap_usd: float = 1.00
    """Ceiling on reported cost.

    Ships in the MVP even though billing does not. Under BYOK the credit being
    spent belongs to the user, so this protects them rather than us.
    """

    stall_repeat_limit: int = 3
    """How many times one instruction to one agent may appear before stopping."""

    no_progress_limit: int = 3
    """Consecutive turns that may produce nothing before stopping."""

    unpriced_call_limit: int = 10
    """How many unpriced calls may accumulate before stopping.

    When a provider stops reporting cost, the spend cap stops protecting
    anyone. Continuing would mean spending the user's money with no way to
    measure it.
    """

    @classmethod
    def from_settings(cls, settings) -> "RunLimits":
        """Build from application settings, so every ceiling is deployable."""
        return cls(
            max_turns=settings.run_max_turns,
            spend_cap_usd=settings.run_spend_cap_usd,
            stall_repeat_limit=settings.run_stall_repeat_limit,
            no_progress_limit=settings.run_no_progress_limit,
            unpriced_call_limit=settings.run_unpriced_call_limit,
        )


@dataclass
class RunState:
    """What the guard has observed so far. Readable for reporting."""

    turns: int = 0
    usage: Usage = field(default_factory=Usage)
    barren_turns: int = 0
    dispatch_counts: Counter[str] = field(default_factory=Counter)

    @property
    def cost_spent(self) -> float:
        return self.usage.known_cost_usd

    @property
    def unpriced_calls(self) -> int:
        return self.usage.unpriced_calls


class RunGuard:
    """Consulted before every dispatch.

    The guard only observes and answers. It does not stop anything itself —
    the orchestrator does — which keeps the decision to end a run in one place.
    """

    def __init__(self, limits: RunLimits | None = None) -> None:
        self.limits = limits or RunLimits()
        self.state = RunState()

    # -- recording --------------------------------------------------------

    def record_usage(self, usage: Usage) -> None:
        """Add the cost of a call, whether or not it produced anything useful.

        Repairs and failed attempts count: they were paid for.
        """
        self.state.usage = self.state.usage + usage

    def record_dispatch(self, decision: SupervisorDecision) -> None:
        """Register a dispatch before the agent runs.

        Recorded first so a stall is caught before paying for the execution
        that would repeat it.
        """
        self.state.turns += 1
        signature = decision.dispatch_signature()
        if signature is not None:
            self.state.dispatch_counts[signature] += 1

    def record_progress(self, new_messages: int) -> None:
        if new_messages > 0:
            self.state.barren_turns = 0
        else:
            self.state.barren_turns += 1

    # -- checking ---------------------------------------------------------

    def check(self) -> TerminationReason | None:
        """The reason this run must stop now, or None to continue.

        Ordered so the most specific diagnosis wins. A stalled run has also
        usually burned turns and money, and telling the user "the same step
        kept repeating" is more useful than "you hit the turn limit".
        """
        if self._stalled():
            return TerminationReason.STALLED
        if self.state.barren_turns >= self.limits.no_progress_limit:
            return TerminationReason.NO_PROGRESS
        if self.state.unpriced_calls >= self.limits.unpriced_call_limit:
            return TerminationReason.UNPRICED_CEILING
        if self.state.cost_spent >= self.limits.spend_cap_usd:
            return TerminationReason.SPEND_CAP
        if self.state.turns >= self.limits.max_turns:
            return TerminationReason.MAX_TURNS
        return None

    def _stalled(self) -> bool:
        if not self.state.dispatch_counts:
            return False
        _, most_common = self.state.dispatch_counts.most_common(1)[0]
        return most_common >= self.limits.stall_repeat_limit

    # -- reporting --------------------------------------------------------

    @property
    def remaining_turns(self) -> int:
        return max(0, self.limits.max_turns - self.state.turns)

    @property
    def remaining_budget_usd(self) -> float:
        return max(0.0, self.limits.spend_cap_usd - self.state.cost_spent)
