"""Writing an agent's instructions by talking about them.

The premise of the product is that someone describes the worker they want in
plain language and gets one. A large empty textarea labelled "system prompt" is
the developer's version of that, and it is the version that loses the people we
are building for: they know what they want the worker to do and have no idea
what a system prompt should look like.

So this is a conversation. The user says what they need, this asks about the
one thing that is genuinely ambiguous, and it writes the instructions. The
instructions come back as a draft rather than being saved, because the user
should see what was written in their name before it becomes their agent.

It deliberately asks at most one question at a time. A form disguised as a
chat — "what is its tone, its audience, its constraints, its output format?" —
is worse than the form was.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..llm import LLMClient, Usage
from ..structured import extract_json

SYSTEM_PROMPT_MAX = 8000
REPLY_MAX = 600

BUILDER_SYSTEM = """\
You help someone design an AI worker by talking to them about it. They describe \
what they want; you write the worker's instructions.

The worker you are designing will be one member of a team. A coordinator gives \
it one task at a time and passes its output to whoever works next. It cannot \
choose who goes next and cannot talk to the other members directly.

# What you produce

`instructions` is what the worker is told about itself, written in the second \
person: "You are a…", "You always…", "You never…". Concrete and specific. State \
what it does, how it decides, what it refuses, and what its output should look \
like so the next member can use it.

# How to behave

- If the description is clear enough to write useful instructions, write them. \
Do not interrogate someone who has already told you what they want.
- If one thing is genuinely ambiguous and would change the instructions, ask \
about that one thing. Never ask two questions at once, and never ask about \
something you could sensibly decide yourself.
- When the user asks for a change, revise the existing instructions rather than \
starting again. Keep what they did not ask you to change.
- `reply` is what the user reads. Say what you wrote or what you need, in one \
or two sentences. Do not repeat the instructions back to them — they can see \
them.

# Response format

Reply with a single JSON object matching this schema and nothing else:

{schema}\
"""

CONTEXT_TEMPLATE = """\
# The worker being designed

Name: {name}
Role: {role}

# Its current instructions

{instructions}

# The conversation so far

{conversation}\
"""

NO_INSTRUCTIONS_YET = "(none yet — this is the first version)"


class BuilderReply(BaseModel):
    """One turn of the agent-building conversation."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(
        min_length=1,
        max_length=REPLY_MAX,
        description="What to show the user. One or two sentences.",
    )
    instructions: str | None = Field(
        default=None,
        max_length=SYSTEM_PROMPT_MAX,
        description=(
            "The worker's full instructions, revised. Null when asking a "
            "question rather than writing."
        ),
    )
    needs_answer: bool = Field(
        default=False,
        description="True when waiting on the user before instructions can be written.",
    )

    @property
    def wrote_instructions(self) -> bool:
        return bool(self.instructions and self.instructions.strip())


@dataclass
class BuilderTurn:
    """What one call produced, and what it cost."""

    reply: BuilderReply
    usage: Usage
    model: str = ""
    attempts: int = 1


class BuilderError(RuntimeError):
    """The builder could not produce a usable reply.

    Raised rather than guessed at: inventing instructions the user never asked
    for would put words in their agent's mouth.
    """


def schema_prompt() -> str:
    import json

    return json.dumps(BuilderReply.model_json_schema(), separators=(",", ":"))


def build_messages(
    name: str,
    role: str,
    instructions: str | None,
    conversation: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Assemble the builder's context.

    The conversation is passed in rather than stored. It is short, the client
    already has it, and keeping it out of the database means one less thing to
    migrate when the shape of this changes — which it will, since this is the
    least settled part of the product.
    """
    rendered = (
        "\n".join(f"{turn['role']}: {turn['content']}" for turn in conversation)
        or "(nothing said yet)"
    )
    content = CONTEXT_TEMPLATE.format(
        name=name or "(unnamed)",
        role=role or "(no role given)",
        instructions=(instructions or "").strip() or NO_INSTRUCTIONS_YET,
        conversation=rendered,
    )
    return BUILDER_SYSTEM.format(schema=schema_prompt()), [
        {"role": "user", "content": content}
    ]


async def refine_agent(
    llm: LLMClient,
    *,
    name: str,
    role: str,
    instructions: str | None,
    conversation: list[dict[str, str]],
    max_repair_attempts: int = 1,
) -> BuilderTurn:
    """Take one turn of the conversation and return the reply and draft.

    Fewer repair attempts than the Supervisor gets. A failure here is one
    stalled message in a form the user can retry, not a run ending halfway —
    so it is not worth spending several paid attempts on.
    """
    system, messages = build_messages(name, role, instructions, conversation)

    usage = Usage()
    last_error = ""
    raw = ""

    for attempt in range(1, max_repair_attempts + 2):
        response = await llm.complete(
            system=system,
            messages=messages,
            temperature=0.3,  # writing, but not freely
            max_tokens=4096,  # instructions can run to several pages
            json_mode=True,
        )
        usage = usage + response.usage
        raw = response.content

        payload = extract_json(raw)
        if payload is None:
            last_error = "The reply was not valid JSON."
        else:
            try:
                reply = BuilderReply.model_validate(payload)
            except ValidationError as exc:
                last_error = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()
                )
            else:
                return BuilderTurn(
                    reply=reply, usage=usage, model=response.model, attempts=attempt
                )

        messages = [
            *messages,
            {"role": "assistant", "content": raw[:1000]},
            {
                "role": "user",
                "content": (
                    f"That was not a valid reply. {last_error} "
                    "Reply again with only the JSON object."
                ),
            },
        ]

    raise BuilderError(f"No usable reply after {max_repair_attempts + 1} attempts: {last_error}")
