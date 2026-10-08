"""One error shape for the whole API.

A client that has to recognise several error formats ends up handling none of
them properly. Everything that fails here comes back as::

    {"error": {"code": "not_found", "message": "..."}}

The code is for the client to branch on; the message is for a person to read.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import DatabaseUnavailable, NotFoundError, RepositoryError
from ..llm import (
    LLMAuthError,
    LLMCreditError,
    LLMError,
    LLMRateLimited,
    LLMUnavailable,
)
from ..observability import REQUEST_ID_HEADER, current_request_id
from .trial import KeyRequired


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    """Quote this when reporting a problem; it finds the whole request."""


class ErrorResponse(BaseModel):
    error: ErrorBody


_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "invalid_request",
    429: "rate_limited",
    500: "internal_error",
}


def _envelope(status_code: int, message: str, code: str | None = None) -> JSONResponse:
    request_id = current_request_id()
    response = JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code or _CODES.get(status_code, "error"),
                "message": message,
                "request_id": request_id,
            }
        },
    )
    if request_id:
        response.headers[REQUEST_ID_HEADER] = request_id
    return response


# How a provider failure reaches a client that is not streaming. Each carries a
# different instruction, because "check your key" is unhelpful when the key is
# fine and the balance is empty.
_PROVIDER_ERRORS: list[tuple[type[LLMError], int, str, str]] = [
    (
        LLMAuthError,
        status.HTTP_400_BAD_REQUEST,
        "key_rejected",
        "OpenRouter rejected this key. Check it has not been revoked.",
    ),
    (
        LLMCreditError,
        status.HTTP_402_PAYMENT_REQUIRED,
        "out_of_credit",
        "This OpenRouter key has no credit left. Add credit or use a free model.",
    ),
    (
        LLMRateLimited,
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        "The model provider is asking us to slow down. Try again in a moment.",
    ),
    (
        LLMUnavailable,
        status.HTTP_502_BAD_GATEWAY,
        "provider_unavailable",
        "The model provider could not be reached. This is not a problem with your account.",
    ),
]


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        response = _envelope(exc.status_code, str(exc.detail))
        # Preserve WWW-Authenticate, which tells a client to re-authenticate
        # rather than treat the failure as permanent.
        for name, value in (exc.headers or {}).items():
            response.headers[name] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'][1:]) or 'body'}: {err['msg']}"
            for err in exc.errors()
        )
        return _envelope(status.HTTP_422_UNPROCESSABLE_ENTITY, problems or "Invalid request")

    @app.exception_handler(NotFoundError)
    async def _missing(request: Request, exc: NotFoundError) -> JSONResponse:
        # Deliberately indistinguishable from "belongs to someone else".
        # Confirming that a row exists but is not yours leaks its existence.
        return _envelope(status.HTTP_404_NOT_FOUND, "Not found")

    @app.exception_handler(KeyRequired)
    async def _key_required(request: Request, exc: KeyRequired) -> JSONResponse:
        # 402 with its own code: the client sends the user to add a key, which
        # is a different next step from every other refusal.
        return _envelope(status.HTTP_402_PAYMENT_REQUIRED, exc.message, "key_required")

    @app.exception_handler(LLMError)
    async def _provider(request: Request, exc: LLMError) -> JSONResponse:
        for error_type, http_status, code, message in _PROVIDER_ERRORS:
            if isinstance(exc, error_type):
                logging.getLogger("agenlate.provider").warning(
                    "provider error", extra={"error_code": code}
                )
                return _envelope(http_status, message, code)
        logging.getLogger("agenlate.provider").warning("provider error")
        return _envelope(
            status.HTTP_502_BAD_GATEWAY,
            "The model provider returned an error.",
            "provider_error",
        )

    @app.exception_handler(DatabaseUnavailable)
    async def _database_down(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
        # Not the user's fault and not a bug in the request, so it says so and
        # says what to do. 503 rather than 500: the condition is temporary.
        logging.getLogger("agenlate.repository").warning(
            "database unreachable", extra={"detail": str(exc)}
        )
        return _envelope(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "We could not reach the database. Nothing was lost — try again in a moment.",
            "unavailable",
        )

    @app.exception_handler(RepositoryError)
    async def _repository(request: Request, exc: RepositoryError) -> JSONResponse:
        # Ours to fix, so it is logged at error level with the detail kept
        # server-side. The client gets a request id and nothing else.
        logging.getLogger("agenlate.repository").exception("database error")
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Something went wrong on our side."
        )
