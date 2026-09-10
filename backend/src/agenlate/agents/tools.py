"""OpenRouter server tools.

These execute on OpenRouter's infrastructure, not ours. The model asks for a
search or a shell command, OpenRouter runs it and feeds the result back, and
the whole loop completes inside a single request — the client receives one
final answer and never sees an intermediate tool call.

That is the reason there is no sandbox in this codebase. Running model-authored
code safely is a hard problem, and doing it at zero infrastructure cost on a
free tier is close to infeasible. This shifts it to someone who already solved
it.

The trade is a real dependency. These identifiers are OpenRouter's, and an
agent layer built on them cannot be pointed at a provider's API directly
without the sandbox coming back.
"""

from __future__ import annotations

from typing import Any

WEB_SEARCH = "openrouter:web_search"
WEB_FETCH = "openrouter:web_fetch"
SHELL = "openrouter:shell"
DATETIME = "openrouter:datetime"

DEFAULT_TOOLS: tuple[str, ...] = (WEB_SEARCH, WEB_FETCH, SHELL, DATETIME)
"""What an agent gets unless told otherwise.

Enough to research, read a page, calculate, and know today's date — the four
things a worker agent most often cannot do on its own.
"""

KNOWN_TOOLS: frozenset[str] = frozenset(
    {
        WEB_SEARCH,
        WEB_FETCH,
        SHELL,
        DATETIME,
        "openrouter:image_generation",
        "openrouter:apply_patch",
        "openrouter:bash",
        "openrouter:fusion",
        "openrouter:advisor",
        "openrouter:subagent",
        "openrouter:tool_search",
    }
)

MAX_TOOL_CALLS = 8
"""Server-side step budget for one dispatch.

OpenRouter allows up to 30. Eight is chosen instead because every step is
billable — web search is priced per result rather than per token — and this is
one agent turn inside a run that will have many. When the budget runs out the
model is asked to answer with what it has, so a low ceiling costs completeness
on that turn rather than failing it.
"""


def resolve_tools(enabled: list[str] | None) -> list[str]:
    """Decide which tools an agent may use.

    ``None`` means every default tool: an agent created without thinking about
    tools should still be capable, so opting out is the deliberate act. An
    empty list means exactly that — no tools — and is honoured.
    """
    if enabled is None:
        return list(DEFAULT_TOOLS)
    return [tool for tool in enabled if tool in KNOWN_TOOLS]


def build_tool_payload(enabled: list[str] | None) -> list[dict[str, Any]] | None:
    """The ``tools`` array for a request, or None when the agent has none."""
    tools = resolve_tools(enabled)
    return [{"type": tool} for tool in tools] if tools else None
