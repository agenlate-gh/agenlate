"""Crash reports from the browser.

When a screen crashes in someone's browser, nothing on the server knows. The
first such bug in the Beta — a page crash under browser translation — was
found only because a tester described the error page, and took a day to trace
from that description. This puts the error itself in the log, where it would
have named the failing operation immediately.

Public and unauthenticated on purpose: a crash can happen on the login page,
or because the session itself is what broke. That makes it a place anyone can
write to the log, so everything is truncated, the volume is limited per
address, and anything key-shaped is redacted before it is logged.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from ..security import redact
from .limits import anonymous_limiter, client_address

router = APIRouter(prefix="/api", tags=["client-errors"])
log = logging.getLogger("agenlate.client")

REPORTS_PER_ADDRESS = 20
REPORT_WINDOW_SECONDS = 600


class ClientErrorReport(BaseModel):
    message: str = Field(max_length=500)
    stack: str = Field(default="", max_length=2000)
    path: str = Field(default="", max_length=300, description="The page it happened on.")
    digest: str = Field(default="", max_length=100, description="Next.js error digest, if any.")


@router.post("/client-errors", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_error(body: ClientErrorReport, request: Request) -> Response:
    # Dropped rather than refused once over the limit: a page stuck in a crash
    # loop should not also be shown an error about reporting its error.
    if anonymous_limiter("client-errors", REPORTS_PER_ADDRESS, REPORT_WINDOW_SECONDS).allow(
        client_address(request)
    ):
        log.warning(
            "browser crash",
            extra={
                # Redacted here, not left to the logging filter: that filter
                # cleans the message text, and these travel as extra fields.
                "client_message": redact(body.message),
                "client_path": redact(body.path),
                "client_stack": redact(body.stack),
                "client_digest": body.digest,
                "user_agent": request.headers.get("user-agent", "")[:200],
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
