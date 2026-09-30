"""Recovering JSON from a model that was asked for JSON.

Shared by the Supervisor, the agent builder and the objective helper, because
all three ask for a structured reply and all meet the same failure: a model
that returns the right object wrapped in something else — a markdown fence, a
sentence of preamble, occasionally both.

Every recovery here is local and free. A repair round trip is charged to the
user, so it is worth being generous at this stage and strict afterwards: the
schema still has to accept whatever comes out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from .llm import LLMClient, Usage

ReplyT = TypeVar("ReplyT", bound=BaseModel)


def extract_json(raw: str) -> dict[str, Any] | None:
    """Find a JSON object in a reply, or None if there is not one.

    Three attempts, cheapest first.
    """
    text = raw.strip()
    if not text:
        return None

    parsed = _try_json(text)
    if parsed is not None:
        return parsed

    # Markdown fences, despite being asked for none.
    if text.startswith("```"):
        fenced = text.split("```")
        if len(fenced) >= 2:
            body = fenced[1]
            if body.startswith("json"):
                body = body[4:]
            parsed = _try_json(body.strip())
            if parsed is not None:
                return parsed

    # An object wrapped in commentary.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        parsed = _try_json(text[start : end + 1])
        if parsed is not None:
            return parsed

    return None


def _try_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


# -- one structured reply, with a bounded repair loop ------------------------


class StructuredReplyError(RuntimeError):
    """No attempt produced a reply that fits the schema."""


@dataclass
class StructuredTurn(Generic[ReplyT]):
    """A validated reply, and what getting it cost."""

    reply: ReplyT
    usage: "Usage"
    model: str
    attempts: int


async def complete_structured(
    llm: "LLMClient",
    reply_model: type[ReplyT],
    *,
    system: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    max_repair_attempts: int = 1,
) -> StructuredTurn[ReplyT]:
    """Ask for a JSON reply and repair it until it validates, or give up.

    Shared by the conversational helpers — the agent builder and the room
    objective helper — which both ask for a small structured reply a user is
    waiting on. Each failed attempt is paid for, so the default allows one
    repair: a stalled message the user can retry costs less than several
    speculative calls.

    Every attempt's usage is summed into the result, including the failed
    ones. They were charged whether or not they helped.
    """
    from .llm import Usage  # deferred: llm imports this module

    usage = Usage()
    last_error = ""
    raw = ""

    for attempt in range(1, max_repair_attempts + 2):
        response = await llm.complete(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        usage = usage + response.usage
        raw = response.content

        payload = extract_json(raw)
        if payload is None:
            last_error = "The reply was not valid JSON."
        else:
            try:
                reply = reply_model.model_validate(payload)
            except ValidationError as exc:
                last_error = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()
                )
            else:
                return StructuredTurn(
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

    raise StructuredReplyError(
        f"No usable reply after {max_repair_attempts + 1} attempts: {last_error}"
    )
