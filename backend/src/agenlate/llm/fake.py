"""A scripted client for tests.

Lets a test drive the Supervisor and orchestrator through an exact sequence of
model outputs — including malformed ones and provider failures — with no API
key and no network.

The script accepts three kinds of entry:

* ``str``          — returned as the response content
* ``LLMResponse``  — returned as-is, for tool calls or specific usage figures
* ``Exception``    — raised, for exercising provider-failure paths
"""

from __future__ import annotations

from typing import Any, Sequence

from .base import LLMClient, LLMResponse, Usage

ScriptEntry = str | LLMResponse | Exception


class ScriptExhausted(AssertionError):
    """The code under test made more calls than the script anticipated.

    An assertion rather than a runtime error: it means the test's expectations
    are wrong, not that the system misbehaved.
    """


class FakeLLM(LLMClient):
    def __init__(
        self,
        script: Sequence[ScriptEntry],
        *,
        usage_per_call: Usage | None = None,
        model: str = "fake/model",
    ) -> None:
        self._script: list[ScriptEntry] = list(script)
        self._usage_per_call = usage_per_call or Usage.for_call(
            prompt_tokens=100, completion_tokens=20, cost_usd=0.0001
        )
        self._model = model
        self.calls: list[dict[str, Any]] = []

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
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
                "tools": tools,
                "max_tool_calls": max_tool_calls,
            }
        )

        if not self._script:
            raise ScriptExhausted(
                f"FakeLLM script ran out after {len(self.calls)} call(s); "
                "the code under test made more calls than the test expected"
            )

        entry = self._script.pop(0)

        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry, LLMResponse):
            return entry
        return LLMResponse(
            content=entry,
            usage=self._usage_per_call.model_copy(),
            model=self._model,
        )

    async def aclose(self) -> None:
        """Nothing to release. Present so callers need no special case."""

    # -- assertions -------------------------------------------------------

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def remaining(self) -> int:
        return len(self._script)

    @property
    def last_call(self) -> dict[str, Any]:
        if not self.calls:
            raise AssertionError("FakeLLM was never called")
        return self.calls[-1]

    def assert_exhausted(self) -> None:
        """Assert every scripted response was consumed.

        Guards the opposite failure to ``ScriptExhausted``: a test that scripts
        four turns but whose subject stops after two still passes its output
        assertions while silently testing less than it claims.
        """
        if self._script:
            raise AssertionError(
                f"{len(self._script)} scripted response(s) were never used; "
                f"only {len(self.calls)} call(s) were made"
            )
