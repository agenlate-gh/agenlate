"""One error shape for the whole API.

A client that has to recognise several error formats ends up handling none of
them properly. Everything that fails here comes back as::

    {"error": {"code": "not_found", "message": "..."}}

The code is for the client to branch on; the message is for a person to read.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import NotFoundError, RepositoryError


class ErrorBody(BaseModel):
    code: str
    message: str


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
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code or _CODES.get(status_code, "error"), "message": message}
        },
    )


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

    @app.exception_handler(RepositoryError)
    async def _repository(request: Request, exc: RepositoryError) -> JSONResponse:
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "The database rejected the request"
        )
