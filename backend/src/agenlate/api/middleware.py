"""Per-request plumbing."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..observability import REQUEST_ID_HEADER, set_request_id

logger = logging.getLogger("agenlate.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gives every request an id, logs its outcome, and returns the id.

    The id comes back in a header so a user reporting a problem can quote it,
    and an inbound one is honoured so a trace survives across services.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = set_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # Logged here because the exception handlers below never see what
            # escapes the middleware stack.
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
