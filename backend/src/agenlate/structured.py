"""Recovering JSON from a model that was asked for JSON.

Shared by the Supervisor and the agent builder, because both ask for a
structured reply and both meet the same failure: a model that returns the right
object wrapped in something else — a markdown fence, a sentence of preamble,
occasionally both.

Every recovery here is local and free. A repair round trip is charged to the
user, so it is worth being generous at this stage and strict afterwards: the
schema still has to accept whatever comes out.
"""

from __future__ import annotations

import json
from typing import Any


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
