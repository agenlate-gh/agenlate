"""Structured logging, request correlation and the error taxonomy."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agenlate.api.errors import install_error_handlers
from agenlate.api.middleware import RequestContextMiddleware
from agenlate.llm import (
    LLMAuthError,
    LLMCreditError,
    LLMError,
    LLMRateLimited,
    LLMUnavailable,
)
from agenlate.observability import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    current_request_id,
    set_request_id,
)

KEY = "sk-or-v1-0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6071"


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    @app.get("/ok")
    async def ok() -> dict:
        logging.getLogger("test").info("handling", extra={"room_id": "room-1"})
        return {"ok": True}

    @app.get("/fail/{kind}")
    async def fail(kind: str) -> dict:
        raise {
            "auth": LLMAuthError("OpenRouter returned 401"),
            "credit": LLMCreditError("OpenRouter returned 402"),
            "rate": LLMRateLimited("OpenRouter returned 429"),
            "down": LLMUnavailable("OpenRouter returned 503"),
            "other": LLMError("something else"),
        }[kind]

    return app


async def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=build_app()), base_url="http://t")


class TestRequestId:
    async def test_every_response_carries_one(self) -> None:
        async with await client() as http:
            response = await http.get("/ok")

        assert response.headers[REQUEST_ID_HEADER]

    async def test_an_inbound_id_is_honoured(self) -> None:
        """So a trace survives across services rather than restarting here."""
        async with await client() as http:
            response = await http.get("/ok", headers={REQUEST_ID_HEADER: "caller-supplied"})

        assert response.headers[REQUEST_ID_HEADER] == "caller-supplied"

    async def test_two_requests_get_different_ids(self) -> None:
        async with await client() as http:
            first = (await http.get("/ok")).headers[REQUEST_ID_HEADER]
            second = (await http.get("/ok")).headers[REQUEST_ID_HEADER]

        assert first != second

    async def test_an_error_response_carries_the_id_too(self) -> None:
        """The case where a user actually needs to quote it."""
        async with await client() as http:
            response = await http.get("/fail/credit")

        assert response.headers[REQUEST_ID_HEADER]
        assert response.json()["error"]["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_the_id_is_readable_without_passing_it_around(self) -> None:
        set_request_id("abc123")

        assert current_request_id() == "abc123"


class TestErrorTaxonomy:
    """Each provider failure needs a different action from the user, so each
    gets its own status and its own wording."""

    @pytest.mark.parametrize(
        ("kind", "status", "code"),
        [
            ("auth", 400, "key_rejected"),
            ("credit", 402, "out_of_credit"),
            ("rate", 429, "rate_limited"),
            ("down", 502, "provider_unavailable"),
            ("other", 502, "provider_error"),
        ],
    )
    async def test_each_class_maps_to_its_own_status(self, kind, status, code) -> None:
        async with await client() as http:
            response = await http.get(f"/fail/{kind}")

        assert response.status_code == status
        assert response.json()["error"]["code"] == code

    async def test_an_empty_balance_does_not_tell_the_user_to_check_their_key(
        self,
    ) -> None:
        """The key is fine. Sending them to check it wastes their time."""
        async with await client() as http:
            message = (await http.get("/fail/credit")).json()["error"]["message"]

        assert "credit" in message.lower()
        assert "revoked" not in message.lower()

    async def test_a_rejected_key_does_not_tell_the_user_to_add_credit(self) -> None:
        async with await client() as http:
            message = (await http.get("/fail/auth")).json()["error"]["message"]

        assert "rejected" in message.lower()

    async def test_a_provider_outage_reassures_rather_than_blames(self) -> None:
        async with await client() as http:
            message = (await http.get("/fail/down")).json()["error"]["message"]

        assert "not a problem with your account" in message.lower()


class TestJsonFormatting:
    @pytest.fixture
    def emitted(self):
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(self.format(record))

        handler = Capture()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(RequestIdFilter())
        logger = logging.getLogger("test.json")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        return logger, records

    def test_each_line_is_json(self, emitted) -> None:
        logger, records = emitted

        logger.info("something happened")

        assert json.loads(records[0])["message"] == "something happened"

    def test_the_request_id_is_on_every_line(self, emitted) -> None:
        logger, records = emitted
        set_request_id("req-42")

        logger.info("something happened")

        assert json.loads(records[0])["request_id"] == "req-42"

    def test_extra_fields_are_carried_through(self, emitted) -> None:
        """So a caller can attach a room id without inventing a message
        format for it."""
        logger, records = emitted

        logger.info("run finished", extra={"room_id": "room-7", "reason": "completed"})

        payload = json.loads(records[0])
        assert payload["room_id"] == "room-7"
        assert payload["reason"] == "completed"

    def test_an_exception_is_included(self, emitted) -> None:
        logger, records = emitted

        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("it failed")

        assert "ValueError" in json.loads(records[0])["exception"]


class TestRedactionSurvivesConfiguration:
    def test_configuring_logging_keeps_secrets_out(self, capsys) -> None:
        """The filters have to be in place before the first request, not
        added once something has gone wrong."""
        configure_logging(json_output=True)

        logging.getLogger("test.redaction.configured").error("key was %s", KEY)

        assert KEY not in capsys.readouterr().out

    def test_configuring_twice_does_not_stack_filters(self) -> None:
        configure_logging()
        configure_logging()

        root = logging.getLogger()
        from agenlate.security import SecretRedactingFilter

        assert sum(isinstance(f, SecretRedactingFilter) for f in root.filters) == 1
        assert sum(isinstance(f, RequestIdFilter) for f in root.filters) == 1
