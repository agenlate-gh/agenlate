"""Writing a room's objective by talking about it.

The objective is the one thing a new user must write before anything happens,
and it is what the Supervisor works from on every turn. Someone who knows
exactly what they want still rarely writes it the way a coordinator needs it:
what the finished result is, how to tell it is finished, and what must not
happen along the way. The people this product is for would otherwise go to
another chat assistant to have it written, paste it back, and learn that
Agenlate is the second stop rather than the first.

So, like the agent builder, this is a short conversation that produces a
draft. Nothing is saved here: the draft goes back to the form, and the user
decides whether to keep it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from .llm import LLMClient, Usage
from .models import OBJECTIVE_MAX, ROOM_NAME_MAX
from .structured import StructuredReplyError, complete_structured

REPLY_MAX = 600

OBJECTIVE_SYSTEM = """\
You help someone set up a room: a team of AI agents working toward one \
objective. They tell you what they want in their own words; you write the \
objective the team will work from.

A coordinator reads the objective before every decision it makes. It uses it \
to choose which agent works next and to decide when the work is finished. It \
cannot ask the person anything while it works unless it stops to do so.

# What you produce

`objective` is written as a brief to the team. It states:
- the finished result — what exactly should exist at the end;
- how to know it is finished, concretely enough that the coordinator can stop;
- anything that must or must not happen along the way, if the person said so.

Plain language. No headings or bullet points unless the result genuinely has \
several parts. As short as it can be while still being unambiguous.

`name`, only when the room has no name yet: two to five words a person would \
recognise on a list of their rooms. Otherwise null.

# How to behave

- If what they said is clear enough to write a useful objective, write it. Do \
not interrogate someone who has already told you what they want.
- If one thing is genuinely ambiguous and would change the result — who it is \
for, how long, which of two things they mean — ask about that one thing. Never \
ask two questions at once, and never ask about something you could sensibly \
decide yourself.
- When they ask for a change, revise the existing objective rather than \
starting again. Keep what they did not ask you to change.
- Never invent facts about them, their business or their audience. Where the \
objective needs something only they know and they have not said it, ask.
- `reply` is what they read: one or two sentences saying what you wrote or \
what you need. Do not repeat the objective back — they can see it.

# Response format

Reply with a single JSON object matching this schema and nothing else:

{schema}\
"""

CONTEXT_TEMPLATE = """\
# The room

Name: {name}

# Its objective so far

{objective}

# The conversation so far

{conversation}\
"""

NO_OBJECTIVE_YET = "(none yet — this is the first version)"
NO_NAME_YET = "(not named yet — suggest one)"


class ObjectiveReply(BaseModel):
    """One turn of the objective-writing conversation."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(
        min_length=1,
        max_length=REPLY_MAX,
        description="What to show the person. One or two sentences.",
    )
    objective: str | None = Field(
        default=None,
        max_length=OBJECTIVE_MAX,
        description="The full objective, revised. Null when asking a question instead.",
    )
    name: str | None = Field(
        default=None,
        max_length=ROOM_NAME_MAX,
        description="A short room name, only when the room has none yet.",
    )
    needs_answer: bool = Field(
        default=False,
        description="True when waiting on the person before an objective can be written.",
    )


@dataclass
class ObjectiveTurn:
    reply: ObjectiveReply
    usage: Usage
    model: str = ""
    attempts: int = 1


class ObjectiveError(RuntimeError):
    """No usable reply. Raised rather than guessed at: an invented objective
    would send the team after something the person never asked for."""


def build_messages(
    name: str | None,
    objective: str | None,
    conversation: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    rendered = (
        "\n".join(f"{turn['role']}: {turn['content']}" for turn in conversation)
        or "(nothing said yet)"
    )
    schema = json.dumps(ObjectiveReply.model_json_schema(), separators=(",", ":"))
    content = CONTEXT_TEMPLATE.format(
        name=(name or "").strip() or NO_NAME_YET,
        objective=(objective or "").strip() or NO_OBJECTIVE_YET,
        conversation=rendered,
    )
    return OBJECTIVE_SYSTEM.format(schema=schema), [{"role": "user", "content": content}]


async def refine_objective(
    llm: LLMClient,
    *,
    name: str | None,
    objective: str | None,
    conversation: list[dict[str, str]],
    max_repair_attempts: int = 1,
) -> ObjectiveTurn:
    """Take one turn of the conversation and return the reply and draft."""
    system, messages = build_messages(name, objective, conversation)
    try:
        turn = await complete_structured(
            llm,
            ObjectiveReply,
            system=system,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,  # an objective is a paragraph or two, not pages
            max_repair_attempts=max_repair_attempts,
        )
    except StructuredReplyError as exc:
        raise ObjectiveError(str(exc)) from None

    reply = turn.reply
    # The name is only asked for when there is none. A model that offers one
    # anyway would rename a room the user already named, so it is dropped.
    if name and name.strip() and reply.name is not None:
        reply = reply.model_copy(update={"name": None})

    return ObjectiveTurn(
        reply=reply, usage=turn.usage, model=turn.model, attempts=turn.attempts
    )
