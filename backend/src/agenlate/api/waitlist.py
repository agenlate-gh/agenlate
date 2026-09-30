"""Joining the Beta waitlist from the landing page.

Public: the people this is for have no account. Three things keep a public
form from becoming a liability:

- The answer is the same whether or not the email was already on the list, so
  the endpoint cannot be used to check who has signed up.
- A hidden field that people never see but form-filling bots do fill in. A
  submission with it filled is accepted and silently dropped, so the bot has
  nothing to learn from.
- A per-address limit, which stops a script in a loop.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from ..db import create_service_client
from ..repository import waitlist as waitlist_repo
from .deps import settings_for
from .limits import anonymous_limiter, client_address

router = APIRouter(prefix="/api", tags=["waitlist"])
log = logging.getLogger("agenlate.waitlist")

JOINS_PER_ADDRESS = 5
JOIN_WINDOW_SECONDS = 600

ACCEPTED = "You're on the list. We'll email you when a place opens up."


class WaitlistRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    source: str = Field(default="landing", min_length=1, max_length=50)
    # The trap. Rendered off-screen and labelled so a person never fills it.
    website: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        local, _, domain = value.partition("@")
        if not local or "." not in domain or " " in value or domain.startswith("."):
            raise ValueError("is not a valid email address")
        return value

    @field_validator("source")
    @classmethod
    def _source(cls, value: str) -> str:
        # Free text from the page; kept to a tidy label so it groups cleanly.
        cleaned = "".join(ch for ch in value.strip().lower() if ch.isalnum() or ch in "-_")
        return cleaned or "landing"


class WaitlistResponse(BaseModel):
    message: str = ACCEPTED


@router.post("/waitlist", response_model=WaitlistResponse, status_code=status.HTTP_202_ACCEPTED)
async def join_waitlist(body: WaitlistRequest, request: Request) -> WaitlistResponse:
    if not anonymous_limiter("waitlist", JOINS_PER_ADDRESS, JOIN_WINDOW_SECONDS).allow(
        client_address(request)
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests from here. Try again in a few minutes.",
        )

    if body.website:
        # A bot. Answer exactly as for a person so it learns nothing.
        log.info("waitlist trap triggered")
        return WaitlistResponse()

    # Service role, because the table is closed to every browser role on
    # purpose; this endpoint is the only way in.
    client = await create_service_client(settings_for(request))
    try:
        await waitlist_repo.join(client, body.email, body.source)
    finally:
        await client.postgrest.aclose()
    return WaitlistResponse()
