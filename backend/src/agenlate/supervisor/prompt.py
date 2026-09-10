"""Turning room state into the Supervisor's context.

The compounding-history problem is the central concern here. The Supervisor is
re-consulted every turn and each consultation replays the transcript, so an
unbounded history means cost grows quadratically over a run: turn twenty pays
for turns one through nineteen all over again.

So history is windowed. What survives is chosen rather than merely trimmed: the
objective and roster live in the system prompt and are never at risk, the
earliest messages are kept because they frame the work, the most recent are
kept because they are what the next decision responds to, and the middle is
elided with a marker saying how much went — a Supervisor that cannot see the
gap will assume the transcript is complete.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..models import Message, RoomWithAgents
from .contract import decision_schema_prompt

# The common approximation is four characters per token. We divide by a
# smaller number so the estimate leans high: underestimating risks overflowing
# the model's context window and failing the call outright, while overestimating
# only trims a little more history than strictly necessary.
_CHARS_PER_TOKEN = 3.5

ELISION_TEMPLATE = "[... {count} earlier message(s) omitted to stay within context ...]"


def estimate_tokens(text: str) -> int:
    """Approximate token count for budgeting.

    Deliberately rough. This decides how much history to include, not what
    anything costs — the actual figures come from the provider and are recorded
    from its response.
    """
    if not text:
        return 0
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


@dataclass(frozen=True)
class PromptBudget:
    """How much transcript the Supervisor is given each turn."""

    history_tokens: int = 6000
    """Ceiling for the rendered transcript."""

    head_messages: int = 2
    """Earliest messages always kept. They frame what the room is doing."""

    min_tail_messages: int = 4
    """Most recent messages always kept, even if that exceeds the budget.

    A Supervisor that cannot see what just happened cannot make a sensible next
    decision, so recency wins over the ceiling. Nothing else does.
    """


SYSTEM_TEMPLATE = """\
You are the Supervisor of a roundtable of AI agents. You do not do the work \
yourself. You decide which agent acts next, and you decide when the work is done.

# Objective

{objective}

# Agents available

{roster}

# How to decide

- "dispatch": give exactly one agent one concrete instruction, then wait. Choose \
the agent whose role fits the next step. Write the instruction so it can be \
carried out without further clarification.
- "complete": the objective has been met. Summarise the result for the user in \
message_to_user.
- "await_user": you are blocked, information is missing that only the user has, \
or the next step is risky enough to need their approval. Explain what you need \
in message_to_user.

# Rules

- One agent per turn. Never dispatch to several at once.
- Do not repeat an instruction that has already been carried out. If an agent's \
output was inadequate, say what was wrong and what to do differently.
- Prefer "complete" as soon as the objective is genuinely met. Continuing past \
that point wastes the user's money.
- If the transcript shows the same step being attempted repeatedly without \
progress, stop and use "await_user" rather than trying again.
- Use only agent ids listed above. Do not invent one.

# Response format

Reply with a single JSON object matching this schema, and nothing else:

{schema}\
"""

TRANSCRIPT_TEMPLATE = """\
# Transcript so far

{transcript}

# Your decision

Respond with the JSON object for your next decision.\
"""

EMPTY_TRANSCRIPT = "(nothing has happened yet — this is the first turn)"


def build_system_prompt(room: RoomWithAgents) -> str:
    """The Supervisor's standing instructions.

    The objective and roster live here rather than in the transcript, so no
    amount of history truncation can put them at risk.
    """
    roster = room.roster() or "(no agents assigned to this room)"
    return SYSTEM_TEMPLATE.format(
        objective=room.room.objective,
        roster=roster,
        schema=decision_schema_prompt(),
    )


def render_history(
    messages: list[Message], budget: PromptBudget | None = None
) -> tuple[str, int]:
    """Render the transcript within budget.

    Returns the rendered text and how many messages were omitted.
    """
    budget = budget or PromptBudget()
    if not messages:
        return EMPTY_TRANSCRIPT, 0

    kept = _select(messages, budget)
    omitted = len(messages) - len(kept)

    lines: list[str] = []
    previous_seq: int | None = None
    for message in kept:
        if previous_seq is not None and message.seq != previous_seq + 1:
            gap = _count_gap(messages, previous_seq, message.seq)
            if gap:
                lines.append(ELISION_TEMPLATE.format(count=gap))
        lines.append(message.render())
        previous_seq = message.seq

    return "\n".join(lines), omitted


def _select(messages: list[Message], budget: PromptBudget) -> list[Message]:
    """Choose which messages survive, newest-first within the budget."""
    head = messages[: budget.head_messages]
    rest = messages[budget.head_messages :]
    if not rest:
        return head

    spent = sum(estimate_tokens(m.render()) for m in head)

    # Walk backwards from the newest: recency is what the next decision
    # responds to, so it is filled first.
    tail: list[Message] = []
    for message in reversed(rest):
        cost = estimate_tokens(message.render())
        within_budget = spent + cost <= budget.history_tokens
        must_keep = len(tail) < budget.min_tail_messages
        if not (within_budget or must_keep):
            break
        tail.append(message)
        spent += cost

    tail.reverse()
    return head + tail


def _count_gap(messages: list[Message], after_seq: int, before_seq: int) -> int:
    return sum(1 for m in messages if after_seq < m.seq < before_seq)


def build_supervisor_messages(
    room: RoomWithAgents,
    messages: list[Message],
    budget: PromptBudget | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Assemble everything the Supervisor is sent for one decision.

    Returns the system prompt and the message list, ready for ``LLMClient``.
    """
    transcript, _ = render_history(messages, budget)
    return (
        build_system_prompt(room),
        [{"role": "user", "content": TRANSCRIPT_TEMPLATE.format(transcript=transcript)}],
    )
