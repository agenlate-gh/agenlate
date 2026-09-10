"""The Supervisor's structured output contract.

Every turn of every session passes through this schema. Three properties matter
more than anything else here:

**It is closed.** The Supervisor may dispatch, finish, or stop and ask. There
is no free-form escape hatch, because a free-form escape hatch is how an
orchestrator talks itself into an infinite loop. ``extra="forbid"`` closes the
other direction: a model inventing a field is a failure to repair, not a value
to ignore.

**It is self-validating.** A decision claiming to dispatch without naming an
agent is rejected at parse time, rather than failing three layers down in the
orchestrator where the cause is no longer obvious.

**It makes invalid states unrepresentable downstream.** Fields that do not
apply to the chosen action are cleared during validation, so no caller can act
on an agent id attached to a decision that was not a dispatch.
"""

from __future__ import annotations

import json
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

REASONING_MAX = 600
INSTRUCTION_MAX = 2000
MESSAGE_MAX = 2000

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = re.compile(r"[.!?,;:\s]+$")


class SupervisorAction(str, Enum):
    """What the Supervisor has decided to do. A closed set, deliberately."""

    DISPATCH = "dispatch"
    """Give one agent one instruction, then re-evaluate."""

    COMPLETE = "complete"
    """The objective is met. End the session."""

    AWAIT_USER = "await_user"
    """Blocked, or the next step is high risk. Hand control back to the human."""


class ObjectiveStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    BLOCKED = "blocked"


class SupervisorDecision(BaseModel):
    """One turn-taking decision."""

    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(
        min_length=1,
        max_length=REASONING_MAX,
        description="Why this decision, in two sentences at most.",
    )
    action: SupervisorAction
    objective_status: ObjectiveStatus
    agent_id: str | None = Field(
        default=None,
        description="Which agent to dispatch to. Required when action is 'dispatch'.",
    )
    instruction: str | None = Field(
        default=None,
        max_length=INSTRUCTION_MAX,
        description=(
            "The single concrete sub-task for that agent. Required when action "
            "is 'dispatch'."
        ),
    )
    message_to_user: str | None = Field(
        default=None,
        max_length=MESSAGE_MAX,
        description=(
            "What to tell the user. Required when action is 'complete' or "
            "'await_user'."
        ),
    )

    @model_validator(mode="after")
    def _enforce_action_shape(self) -> "SupervisorDecision":
        if self.action is SupervisorAction.DISPATCH:
            if not (self.agent_id or "").strip():
                raise ValueError("action 'dispatch' requires agent_id")
            if not (self.instruction or "").strip():
                raise ValueError("action 'dispatch' requires a non-empty instruction")
            # A dispatch says nothing to the user; the agent's output does.
            self.message_to_user = None
        else:
            if not (self.message_to_user or "").strip():
                raise ValueError(
                    f"action '{self.action.value}' requires message_to_user"
                )
            # Cleared rather than rejected. A model that fills these in while
            # choosing to finish is confused but not wrong, and a repair round
            # trip costs real money; clearing them means no caller downstream
            # can mistake this for a dispatch.
            self.agent_id = None
            self.instruction = None
        return self

    @property
    def is_dispatch(self) -> bool:
        return self.action is SupervisorAction.DISPATCH

    @property
    def is_terminal(self) -> bool:
        """Whether this decision ends the run."""
        return self.action is not SupervisorAction.DISPATCH

    def dispatch_signature(self) -> str | None:
        """Identity of this dispatch, for stall detection.

        Returns None for decisions that are not dispatches, which have no
        signature to compare.

        Normalised before comparison because a Supervisor going in circles
        usually rephrases rather than repeating itself word for word. Case,
        internal spacing and trailing punctuation are all noise for this
        purpose; anything beyond that is a genuinely different instruction and
        should not collide.
        """
        if not self.is_dispatch:
            return None
        instruction = _WHITESPACE.sub(" ", (self.instruction or "").strip().lower())
        instruction = _TRAILING_PUNCTUATION.sub("", instruction)
        return f"{self.agent_id}::{instruction}"


def decision_json_schema() -> dict:
    """The JSON Schema handed to the model.

    Generated from the model itself so the prompt cannot drift out of step with
    what is actually accepted. A hand-written copy would be correct on the day
    it was written and quietly wrong thereafter.
    """
    return SupervisorDecision.model_json_schema()


def decision_schema_prompt() -> str:
    return json.dumps(decision_json_schema(), indent=2)
