"""Trial runs: a new account's first few runs, on Agenlate's key.

Agenlate is bring-your-own-key, and stays that way. But a key is a lot to ask
of someone who has not yet seen the product do anything, so a request that
arrives without one is served from our key instead — a limited number of
times, on one cheap model, under a spending cap much lower than a user sets
for themselves.

This is the only place our key is read. The endpoints that use it ask here for
a grant and get back the key, the model they must use, and the use to give
back if nothing came of it. With no key configured the trial is off and every
one of those requests is refused the way it always was: add your own key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import CurrentUser, current_user
from ..config import Settings
from ..db import create_service_client
from ..repository import trial as trial_repo
from .deps import settings_for

router = APIRouter(prefix="/api/trial", tags=["trial"])
log = logging.getLogger("agenlate.trial")

RUN = "run"
ASSIST = "assist"

NO_KEY = "Add your OpenRouter key to do this."
RUNS_USED = (
    "You have used your free runs. Add your own OpenRouter key to keep going — "
    "your rooms and agents stay exactly as they are."
)
ASSISTS_USED = (
    "You have used the free help that comes with a new account. Add your own "
    "OpenRouter key to keep using it."
)
BETA_USED = (
    "The free runs for this Beta have all been used. Add your own OpenRouter "
    "key to keep going."
)
TRIAL_DOWN = (
    "The free runs are not available right now. Add your own OpenRouter key to "
    "keep going. This one was not counted against you."
)


class KeyRequired(Exception):
    """The request carried no key and the trial cannot cover it.

    Its own exception rather than an HTTPException so the client gets a code
    it can branch on: every message here ends at the same place, the screen
    where a key is added.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class TrialGrant:
    """Permission to make one request on our key."""

    api_key: str
    model: str
    use_id: str
    remaining: int


def is_enabled(settings: Settings) -> bool:
    return settings.trial_openrouter_key is not None


async def claim_trial(
    settings: Settings, user_id: str, kind: str, room_id: str | None = None
) -> TrialGrant:
    """Take one trial use for this account, or raise ``KeyRequired``."""
    if settings.trial_openrouter_key is None:
        raise KeyRequired(NO_KEY)

    per_user, total = (
        (settings.trial_runs_per_user, settings.trial_total_runs)
        if kind == RUN
        else (settings.trial_assists_per_user, settings.trial_total_assists)
    )

    # Service role, because the table is closed to every browser role: an
    # account must not be able to read, add or remove its own uses.
    client = await create_service_client(settings)
    try:
        claim = await trial_repo.claim(
            client,
            user_id=user_id,
            kind=kind,
            room_id=room_id,
            user_limit=per_user,
            total_limit=total,
        )
    finally:
        await client.postgrest.aclose()

    if not claim.claimed or claim.use_id is None:
        if claim.outcome == "total_limit":
            log.warning("trial total reached", extra={"kind": kind})
            raise KeyRequired(BETA_USED)
        raise KeyRequired(RUNS_USED if kind == RUN else ASSISTS_USED)

    return TrialGrant(
        api_key=settings.trial_openrouter_key.get_secret_value(),
        model=settings.trial_model,
        use_id=claim.use_id,
        remaining=claim.remaining,
    )


async def release_trial(settings: Settings, use_id: str) -> None:
    """Give a use back. Never raises.

    Called when a request on our key failed for a reason that was ours — the
    key was refused or out of credit — so the user is not charged a free run
    for our outage. A failure to give it back costs them one use, which is
    not worth failing the response over.
    """
    try:
        client = await create_service_client(settings)
        try:
            await trial_repo.release(client, use_id)
        finally:
            await client.postgrest.aclose()
    except Exception:
        log.exception("could not release a trial use")


class TrialStatus(BaseModel):
    enabled: bool = Field(description="Whether free runs are on offer at all.")
    runs_total: int = Field(description="How many free runs a new account gets.")
    runs_remaining: int
    model: str | None = Field(
        default=None, description="The one model free runs use, when enabled."
    )


@router.get("", response_model=TrialStatus)
async def trial_status(
    request: Request, user: CurrentUser = Depends(current_user)
) -> TrialStatus:
    """How many free runs this account has left."""
    settings = settings_for(request)
    if not is_enabled(settings):
        return TrialStatus(enabled=False, runs_total=0, runs_remaining=0)

    client = await create_service_client(settings)
    try:
        used = await trial_repo.used(client, user.id, RUN)
    finally:
        await client.postgrest.aclose()

    total = settings.trial_runs_per_user
    return TrialStatus(
        enabled=True,
        runs_total=total,
        runs_remaining=max(0, total - used),
        model=settings.trial_model,
    )
