"""Provider-agnostic LLM interface.

Everything above this module — the Supervisor, the orchestrator, the billing
recorder — depends only on what is defined here. Nothing above it imports
anything OpenRouter-specific.

The seam exists so the codebase is not married to one provider. It is not an
invitation to add providers: OpenRouter is the only implementation in the MVP,
and the test fake is the second, which is what proves the abstraction is real
rather than decorative.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Usage(BaseModel):
    """What a call cost, in the provider's own numbers.

    ``cost_usd`` is the amount the provider reported. It is nullable on
    purpose: null means the provider told us nothing, which is not the same as
    telling us zero. Free models exist and report ``0``; a missing figure means
    we do not know, and recording that as zero would silently understate what a
    user spent.

    Because a run makes many calls, a total has to survive a mix of the two.
    Rather than let one unknown poison the whole figure or quietly vanish into
    it, a total carries both: ``cost_usd`` is the sum of what we do know, and
    ``unpriced_calls`` says how many calls we do not.
    """

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    calls: int = Field(default=0, ge=0)
    unpriced_calls: int = Field(default=0, ge=0)
    server_tool_calls: int = Field(default=0, ge=0)
    """Server tool steps OpenRouter executed, when it says.

    Best effort, and often zero even when tools ran: ``server_tool_use`` came
    back null on every request measured, including one where a web search
    demonstrably executed. Do not treat this as a count of what happened.

    It is kept because the cost question it was added to answer is now settled
    the other way, and settled well. A free model with no tools reports a cost
    of exactly zero; the same free model performing one real web search reports
    $0.007. Since the model itself is free, that figure can only be the search
    charge — so **tool charges are inside the reported cost**, and reading that
    cost is enough. Tool volume, if it is ever needed, has to come from
    somewhere else.
    """

    @classmethod
    def for_call(
        cls,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float | None = None,
        server_tool_calls: int = 0,
    ) -> "Usage":
        """Usage for a single provider response."""
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            calls=1,
            unpriced_calls=0 if cost_usd is not None else 1,
            server_tool_calls=server_tool_calls,
        )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def known_cost_usd(self) -> float:
        """The portion of the cost we actually know.

        Named so that treating an unknown cost as zero has to be a deliberate
        choice at the call site. Check ``has_unknown_cost`` before trusting it
        as a total.
        """
        return self.cost_usd if self.cost_usd is not None else 0.0

    @property
    def has_unknown_cost(self) -> bool:
        return self.unpriced_calls > 0

    def __add__(self, other: "Usage") -> "Usage":
        if self.cost_usd is None and other.cost_usd is None:
            combined_cost: float | None = None
        else:
            combined_cost = (self.cost_usd or 0.0) + (other.cost_usd or 0.0)

        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost_usd=combined_cost,
            calls=self.calls + other.calls,
            unpriced_calls=self.unpriced_calls + other.unpriced_calls,
            server_tool_calls=self.server_tool_calls + other.server_tool_calls,
        )


class LLMResponse(BaseModel):
    """One completion."""

    content: str
    usage: Usage = Field(default_factory=Usage)
    model: str = ""
    # The provider's id for this generation, kept so a usage row can be
    # reconciled against the provider's own record later.
    generation_id: str | None = None
    # Tool calls the model wants executed, passed through untouched. Empty for
    # an ordinary completion.
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMError(RuntimeError):
    """A provider-level failure: transport, authentication, or rate limiting.

    Distinct from a malformed *response*, which is the Supervisor's problem to
    repair rather than the client's.
    """


class LLMAuthError(LLMError):
    """The key was rejected. The user must correct it; retrying will not help."""


class LLMCreditError(LLMError):
    """The key is valid but has no credit left.

    Separate from an auth failure because the action is different: add credit
    rather than check the key. Telling a user to check a key that is fine sends
    them looking in the wrong place.
    """


class LLMRateLimited(LLMError):
    """Too many requests. Unlike the others, waiting actually fixes this."""


class LLMUnavailable(LLMError):
    """The provider is down or unreachable. Nothing the user can do."""


@runtime_checkable
class LLMClient(Protocol):
    """The only surface the orchestration core depends on."""

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
        max_tool_calls: int | None = None,
        reasoning: bool = False,
    ) -> LLMResponse: ...

    async def aclose(self) -> None:
        """Release whatever the client holds.

        Part of the contract rather than an implementation detail: a caller
        should not have to ask whether a client needs closing, and a fake that
        cannot be closed diverges from the thing it stands in for.
        """
        ...
