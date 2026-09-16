"""OpenRouter client. The only concrete provider implementation.

Under BYOK the key belongs to the user, arrives per run, and is never
persisted. The constructor therefore takes it as an argument and never reads
the environment: an instance is built per session, not per process.

Key safety is not incidental here. The most likely way a key escapes is not
someone logging it deliberately — it is an unhandled error whose string form
happens to contain a request, a header dict, or an echoed body. So the key is
held in a ``SecretStr``, headers are built per request rather than stored, and
every message this module raises is scrubbed before it leaves.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import SecretStr

from .base import LLMClient, LLMError, LLMResponse, Usage

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Long enough for a slow model on a large context; short enough that a hung
# provider does not hold a Render worker open indefinitely.
DEFAULT_TIMEOUT = 120.0


class OpenRouterClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "anthropic/claude-sonnet-4.5",
        timeout: float = DEFAULT_TIMEOUT,
        app_url: str = "https://agenlate.com",
        app_title: str = "Agenlate",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("an OpenRouter API key is required (BYOK)")

        self._api_key = SecretStr(api_key.strip())
        self.model = model
        self._timeout = timeout
        self._app_url = app_url
        self._app_title = app_title
        # A run makes many calls. Reusing one connection pool across them
        # avoids a fresh TLS handshake per turn.
        self._http = http_client
        self._owns_http = http_client is None

    # -- key handling -----------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Built per request and never stored, so no attribute of this object
        holds the key in plain text."""
        return {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "HTTP-Referer": self._app_url,
            "X-Title": self._app_title,
            "Content-Type": "application/json",
        }

    def _scrub(self, text: str) -> str:
        """Remove the key from anything on its way into an exception or log.

        Defence in depth. Nothing should be putting it there, but this module
        is the last point at which we can be sure.
        """
        secret = self._api_key.get_secret_value()
        return text.replace(secret, "***") if secret in text else text

    def _fail(self, message: str) -> LLMError:
        return LLMError(self._scrub(message))

    def __repr__(self) -> str:
        return f"OpenRouterClient(model={self.model!r}, api_key=SecretStr('**********'))"

    __str__ = __repr__

    # -- lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    # -- completion -------------------------------------------------------

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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            # Server-side step budget. Every step is billable, so this is the
            # ceiling on what one agent turn can spend on tools.
            if max_tool_calls is not None:
                payload["max_tool_calls"] = max_tool_calls

        try:
            response = await self._client().post(
                ENDPOINT, json=payload, headers=self._headers()
            )
        except httpx.TimeoutException as exc:
            raise self._fail(f"OpenRouter timed out after {self._timeout}s") from None
        except httpx.HTTPError as exc:
            # `from None` rather than `from exc`: the chained traceback would
            # carry httpx's own request representation along with it.
            raise self._fail(f"OpenRouter request failed: {type(exc).__name__}") from None

        if response.status_code != 200:
            raise self._fail(self._describe_failure(response))

        try:
            data = response.json()
        except ValueError:
            raise self._fail("OpenRouter returned a non-JSON response") from None

        return self._parse(data)

    def _describe_failure(self, response: httpx.Response) -> str:
        """Surface the provider's own wording.

        Under BYOK most failures belong to the user's key — invalid, out of
        credit, or not permitted for the requested model — and a generic
        message leaves them with nothing to act on.
        """
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or "")
                elif isinstance(error, str):
                    detail = error
        except ValueError:
            detail = response.text[:500]

        return f"OpenRouter returned {response.status_code}" + (f": {detail}" if detail else "")

    def _parse(self, data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise self._fail("OpenRouter response contained no choices")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise self._fail("OpenRouter response contained no message")

        # Content is null when the model answers with tool calls instead.
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            tool_calls = []

        return LLMResponse(
            content=content,
            usage=self._parse_usage(data.get("usage")),
            model=data.get("model") or self.model,
            generation_id=data.get("id"),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _parse_usage(raw: Any) -> Usage:
        """Read the provider's own figures, including what it charged.

        The reported cost is the number the margin is applied to. It is read
        rather than derived from token counts on purpose: OpenRouter bills some
        things per call rather than per token — server tools among them — so a
        token-derived price silently misses real spending and breaks whenever
        their pricing changes.

        A cost that is absent or not a number becomes None, which records the
        request as unpriced. It never becomes zero.
        """
        if not isinstance(raw, dict):
            return Usage.for_call()

        cost = raw.get("cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            cost = None

        return Usage.for_call(
            prompt_tokens=_as_int(raw.get("prompt_tokens")),
            completion_tokens=_as_int(raw.get("completion_tokens")),
            cost_usd=float(cost) if cost is not None else None,
            server_tool_calls=_count_tool_use(raw.get("server_tool_use")),
        )


def _count_tool_use(raw: Any) -> int:
    """Total server tool steps from OpenRouter's per-tool counts.

    Reported as a mapping such as {"web_search_requests": 2}. The individual
    tool names are not enumerated here because new ones appear regularly and an
    unknown key should still be counted rather than silently dropped.
    """
    if not isinstance(raw, dict):
        return 0
    return sum(_as_int(value) for value in raw.values())


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))
