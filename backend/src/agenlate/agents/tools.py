"""OpenRouter server tools.

These execute on OpenRouter's infrastructure, not ours. The model asks for a
search or a page fetch, OpenRouter runs it and feeds the result back, and the
whole loop completes inside a single request — the client receives one final
answer and never sees an intermediate tool call.

Two things about this were established by asking the live API rather than
reading the documentation, and both shape what is here.

**Not every tool works on this endpoint.** ``shell``, ``bash``, ``apply_patch``
and ``tool_search`` are rejected by ``/chat/completions`` with "only supported
for: responses, anthropic-messages". Sandboxed code execution therefore is not
available to us without moving to a different API surface, which is a real
piece of work and not one the Beta needs. Agents can research; they cannot run
code.

**Enabling tools is not free.** Measured against Sonnet: a request with no
tools carries 10 prompt tokens, and the first tool takes that to about 960 —
roughly $0.003 a call. Each further tool adds only 80–100 more. The decision
that costs money is tools or no tools, not which ones, and it is paid on every
call because the definitions are re-sent each time.
"""

from __future__ import annotations

from typing import Any

WEB_SEARCH = "openrouter:web_search"
WEB_FETCH = "openrouter:web_fetch"
DATETIME = "openrouter:datetime"
IMAGE_GENERATION = "openrouter:image_generation"

SUPPORTED_TOOLS: frozenset[str] = frozenset(
    {WEB_SEARCH, WEB_FETCH, DATETIME, IMAGE_GENERATION}
)
"""What ``/chat/completions`` actually accepts.

Confirmed by probing the live API. Sending anything outside this set fails the
whole request with a 400, taking the agent's turn with it, so unknown and
unsupported identifiers are filtered out before the request is built.
"""

UNSUPPORTED_ON_CHAT_COMPLETIONS: frozenset[str] = frozenset(
    {
        "openrouter:shell",
        "openrouter:bash",
        "openrouter:apply_patch",
        "openrouter:tool_search",
        "openrouter:fusion",
        "openrouter:advisor",
        "openrouter:subagent",
    }
)
"""Real tools that this endpoint rejects.

Named rather than merely absent, so that a future move to the responses API
has a list of what becomes available, and so an agent configured with one of
them fails quietly rather than fatally.
"""

DEFAULT_TOOLS: tuple[str, ...] = (WEB_SEARCH, WEB_FETCH, DATETIME)
"""What an agent gets unless told otherwise.

Research is the thing agents most often cannot do from memory, and the whole
premise of a worker agent is that it can find something out. Since the fixed
overhead is paid the moment any tool is on, adding fetch and datetime alongside
search costs little more than search alone.

Turning them off for an agent that only works from the transcript — a writer, a
critic — is a real saving, which is why it is a per-agent setting.
"""

MAX_TOOL_CALLS = 4
"""Server-side step budget for one dispatch.

OpenRouter allows up to 30. Four is chosen instead, because a measured web
search costs about $0.007 — more than an entire conversation on a free model.
Tool use, not tokens, is the dominant cost for a Beta user, and this budget is
per agent turn in a run that will have many.

When the budget runs out the model is asked to answer with what it has, so a
low ceiling costs completeness on that turn rather than failing it.
"""


def resolve_tools(enabled: list[str] | None) -> list[str]:
    """Decide which tools an agent may use.

    ``None`` means the defaults: an agent created without thinking about tools
    should still be able to find something out, so opting out is the deliberate
    act. An empty list means exactly that — no tools — and is honoured.

    Anything unsupported is dropped rather than forwarded. One bad identifier
    fails the entire request, and losing an agent's turn to a stale name is a
    worse outcome than that agent going without the tool.
    """
    if enabled is None:
        return list(DEFAULT_TOOLS)
    return [tool for tool in enabled if tool in SUPPORTED_TOOLS]


def build_tool_payload(enabled: list[str] | None) -> list[dict[str, Any]] | None:
    """The ``tools`` array for a request, or None when the agent has none."""
    tools = resolve_tools(enabled)
    return [{"type": tool} for tool in tools] if tools else None
