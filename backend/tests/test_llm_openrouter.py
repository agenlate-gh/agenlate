"""The OpenRouter client. No network: every request is intercepted by respx."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from agenlate.llm import LLMError, Usage
from agenlate.llm.openrouter import ENDPOINT, OpenRouterClient

KEY = "sk-or-v1-supersecretkeyvalue0000000000"

# Constructing an httpx.AsyncClient builds an SSL context, which on Windows
# means loading the system certificate store — around half a second, per
# client. Sharing one across the module keeps this file fast; the two tests
# that are about client ownership construct their own.
_shared_http: httpx.AsyncClient | None = None


@pytest_asyncio.fixture(scope="module", autouse=True)
async def shared_http():
    global _shared_http
    _shared_http = httpx.AsyncClient()
    yield
    await _shared_http.aclose()
    _shared_http = None


def make_client(**kwargs) -> OpenRouterClient:
    """Client under test, reusing the module's HTTP client unless told not to."""
    kwargs.setdefault("http_client", _shared_http)
    return OpenRouterClient(KEY, **kwargs)


def completion(
    *,
    content: str = "hello",
    usage: dict | None = None,
    tool_calls: list | None = None,
) -> dict:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
        message["content"] = None
    return {
        "id": "gen-abc123",
        "model": "anthropic/claude-sonnet-4.5",
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": usage if usage is not None else {
            "prompt_tokens": 1200,
            "completion_tokens": 300,
            "total_tokens": 1500,
            "cost": 0.004521,
        },
    }


async def call(client: OpenRouterClient, **kwargs):
    return await client.complete(
        system="you are the supervisor",
        messages=[{"role": "user", "content": "the objective"}],
        **kwargs,
    )


class TestConstruction:
    def test_rejects_an_empty_key(self) -> None:
        with pytest.raises(ValueError, match="key is required"):
            OpenRouterClient("")

    def test_rejects_a_whitespace_key(self) -> None:
        with pytest.raises(ValueError):
            OpenRouterClient("   ")


class TestSuccessfulCompletion:
    @respx.mock
    async def test_returns_content_model_and_generation_id(self) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = make_client()

        response = await call(client)

        assert response.content == "hello"
        assert response.model == "anthropic/claude-sonnet-4.5"
        assert response.generation_id == "gen-abc123"
        await client.aclose()

    @respx.mock
    async def test_captures_the_reported_cost(self) -> None:
        """The reported cost is what the margin will be applied to. It is read
        from the response, never derived from token counts."""
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = make_client()

        response = await call(client)

        assert response.usage.cost_usd == pytest.approx(0.004521)
        assert response.usage.has_unknown_cost is False
        assert response.usage.total_tokens == 1500
        await client.aclose()

    @respx.mock
    async def test_sends_attribution_headers(self) -> None:
        route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = make_client(app_title="Agenlate", app_url="https://agenlate.com")

        await call(client)

        headers = route.calls.last.request.headers
        assert headers["x-title"] == "Agenlate"
        assert headers["http-referer"] == "https://agenlate.com"
        await client.aclose()

    @respx.mock
    async def test_system_prompt_leads_the_message_list(self) -> None:
        route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = make_client()

        await call(client)

        sent = route.calls.last.request.read().decode()
        assert '"role": "system"' in sent.replace('"role":"system"', '"role": "system"')
        await client.aclose()

    @respx.mock
    async def test_json_mode_sets_response_format(self) -> None:
        import json

        route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = make_client()

        await call(client, json_mode=True)

        body = json.loads(route.calls.last.request.read())
        assert body["response_format"] == {"type": "json_object"}
        await client.aclose()

    @respx.mock
    async def test_tools_are_passed_through(self) -> None:
        import json

        route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = make_client()

        await call(client, tools=[{"type": "openrouter:web_search"}])

        body = json.loads(route.calls.last.request.read())
        assert body["tools"] == [{"type": "openrouter:web_search"}]
        await client.aclose()

    @respx.mock
    async def test_tool_calls_come_back_with_empty_content(self) -> None:
        """A model answering with tool calls returns null content, which must
        not become the string 'None'."""
        calls = [{"id": "t1", "type": "function", "function": {"name": "search"}}]
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(200, json=completion(tool_calls=calls))
        )
        client = make_client()

        response = await call(client)

        assert response.content == ""
        assert response.wants_tools is True
        assert response.tool_calls == calls
        await client.aclose()


class TestCostReporting:
    @respx.mock
    @pytest.mark.parametrize(
        "usage_block",
        [
            {"prompt_tokens": 10, "completion_tokens": 5},           # no cost key
            {"prompt_tokens": 10, "completion_tokens": 5, "cost": None},
            {"prompt_tokens": 10, "completion_tokens": 5, "cost": "0.01"},  # string
            {"prompt_tokens": 10, "completion_tokens": 5, "cost": -1},      # nonsense
        ],
    )
    async def test_unreported_cost_becomes_unpriced_never_zero(self, usage_block) -> None:
        """Recording a missing cost as zero would understate what the user
        spent. The request is marked unpriced instead."""
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(200, json=completion(usage=usage_block))
        )
        client = make_client()

        response = await call(client)

        assert response.usage.cost_usd is None
        assert response.usage.has_unknown_cost is True
        assert response.usage.unpriced_calls == 1
        await client.aclose()

    @respx.mock
    async def test_zero_cost_is_priced(self) -> None:
        """Free models report zero, which is a real answer, not a missing one."""
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json=completion(usage={"prompt_tokens": 10, "completion_tokens": 5, "cost": 0}),
            )
        )
        client = make_client()

        response = await call(client)

        assert response.usage.cost_usd == 0.0
        assert response.usage.has_unknown_cost is False
        await client.aclose()

    @respx.mock
    async def test_missing_usage_block_is_handled(self) -> None:
        payload = completion()
        del payload["usage"]
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = make_client()

        response = await call(client)

        assert response.usage.has_unknown_cost is True
        assert response.usage.total_tokens == 0
        await client.aclose()


class TestProviderFailures:
    @respx.mock
    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (401, "No auth credentials found"),
            (402, "Insufficient credits"),
            (429, "Rate limit exceeded"),
        ],
    )
    async def test_surfaces_the_providers_own_message(self, status, message) -> None:
        """Under BYOK most failures belong to the user's key, and a generic
        message leaves them nothing to act on."""
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(status, json={"error": {"message": message}})
        )
        client = make_client()

        with pytest.raises(LLMError) as exc_info:
            await call(client)

        assert str(status) in str(exc_info.value)
        assert message in str(exc_info.value)
        await client.aclose()

    @respx.mock
    async def test_non_json_error_body_is_still_reported(self) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(502, text="upstream down"))
        client = make_client()

        with pytest.raises(LLMError, match="502"):
            await call(client)
        await client.aclose()

    @respx.mock
    async def test_non_json_success_body_fails_clearly(self) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
        client = make_client()

        with pytest.raises(LLMError, match="non-JSON"):
            await call(client)
        await client.aclose()

    @respx.mock
    @pytest.mark.parametrize(
        "payload",
        [
            {"id": "g", "choices": []},
            {"id": "g"},
            {"id": "g", "choices": [{"finish_reason": "stop"}]},
        ],
    )
    async def test_malformed_success_payloads_raise(self, payload) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = make_client()

        with pytest.raises(LLMError):
            await call(client)
        await client.aclose()

    @respx.mock
    async def test_timeout_is_reported_as_a_provider_error(self) -> None:
        respx.post(ENDPOINT).mock(side_effect=httpx.ConnectTimeout("timed out"))
        client = make_client(timeout=1.0)

        with pytest.raises(LLMError, match="timed out"):
            await call(client)
        await client.aclose()

    @respx.mock
    async def test_transport_failure_is_reported(self) -> None:
        respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("no route"))
        client = make_client()

        with pytest.raises(LLMError, match="request failed"):
            await call(client)
        await client.aclose()


class TestKeyNeverEscapes:
    """The likeliest way a key leaks is not a deliberate log line — it is an
    unhandled error whose string form happens to contain the request.
    """

    def test_repr_masks_the_key(self) -> None:
        assert KEY not in repr(make_client())
        assert "**********" in repr(make_client())

    def test_str_masks_the_key(self) -> None:
        assert KEY not in str(make_client())

    def test_key_is_not_readable_from_instance_attributes(self) -> None:
        client = make_client()

        for value in vars(client).values():
            assert KEY not in str(value)
            assert KEY not in repr(value)

    @respx.mock
    @pytest.mark.parametrize(
        "failure",
        [
            httpx.Response(401, json={"error": {"message": "bad key"}}),
            httpx.Response(500, text="server error"),
            httpx.Response(200, text="not json"),
            httpx.Response(200, json={"choices": []}),
        ],
    )
    async def test_no_error_path_leaks_the_key(self, failure) -> None:
        respx.post(ENDPOINT).mock(return_value=failure)
        client = make_client()

        with pytest.raises(LLMError) as exc_info:
            await call(client)

        assert KEY not in str(exc_info.value)
        assert KEY not in repr(exc_info.value)
        await client.aclose()

    @respx.mock
    async def test_a_provider_echoing_the_key_back_is_scrubbed(self) -> None:
        """If the provider ever reflects the key in an error body, it must not
        pass through into our exception."""
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                400, json={"error": {"message": f"invalid key {KEY} supplied"}}
            )
        )
        client = make_client()

        with pytest.raises(LLMError) as exc_info:
            await call(client)

        assert KEY not in str(exc_info.value)
        assert "***" in str(exc_info.value)
        await client.aclose()

    @respx.mock
    async def test_exception_chain_carries_no_request_object(self) -> None:
        """A chained httpx exception would drag its own request repr along."""
        respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("no route"))
        client = make_client()

        with pytest.raises(LLMError) as exc_info:
            await call(client)

        assert exc_info.value.__cause__ is None
        await client.aclose()


class TestConnectionReuse:
    @respx.mock
    async def test_repeated_calls_share_one_http_client(self) -> None:
        """A run makes many calls; a fresh connection pool per turn would mean
        a TLS handshake per turn."""
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        client = OpenRouterClient(KEY)  # no injection: exercise lazy creation

        await call(client)
        first = client._client()
        await call(client)

        assert client._client() is first
        await client.aclose()

    @respx.mock
    async def test_an_injected_client_is_not_closed_by_us(self) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=completion()))
        injected = httpx.AsyncClient()
        client = make_client(http_client=injected)

        await call(client)
        await client.aclose()

        assert injected.is_closed is False
        await injected.aclose()


class TestProtocolConformance:
    def test_satisfies_the_llm_client_protocol(self) -> None:
        from agenlate.llm import LLMClient

        assert isinstance(make_client(), LLMClient)
