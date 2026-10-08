"""Starting a roundtable and streaming it back.

The run happens inside this request. Render's free tier has no background
workers, so there is nowhere else to put it — and an open connection is
actually convenient here, because it keeps the instance from sleeping for the
duration and gives the client a natural cancellation signal.

The user's OpenRouter key arrives in the request body and lives in memory for
exactly as long as this handler does. It is not written to the database, not
logged, and not cached.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, SecretStr, field_validator
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..db import NotFoundError
from ..llm.openrouter import OpenRouterClient
from ..models import RoomStatus
from ..orchestrator import RunFinished, run_room
from ..repository import messages as messages_repo
from ..repository import rooms as rooms_repo
from ..security import looks_like_openrouter_key
from ..store import SupabaseRunStore
from ..supervisor import RunLimits, TerminationReason
from .deps import settings_for, user_db
from .limits import run_limiter
from .sse import stream
from .trial import RUN, TRIAL_DOWN, TrialGrant, claim_trial, release_trial

router = APIRouter(prefix="/api/rooms", tags=["runs"])

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


class RunRequest(BaseModel):
    """What starting a run needs.

    The key is typed as a secret so that anything which stringifies this model
    — a validation error, a log line, an exception repr — masks it rather than
    printing it.
    """

    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "The caller's own OpenRouter key. Left out, the run is one of the "
            "account's free trial runs, if it has any left."
        ),
    )
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)
    max_turns: int | None = Field(default=None, gt=0, le=50)
    spend_cap_usd: float | None = Field(default=None, gt=0, le=20)

    @field_validator("api_key")
    @classmethod
    def _shape(cls, value: SecretStr | None) -> SecretStr | None:
        """Reject an obviously malformed key before starting a run.

        The message never quotes the value: a validation error that echoed its
        input would put the key into the response body.
        """
        if value is None:
            return None
        if not looks_like_openrouter_key(value.get_secret_value()):
            raise ValueError("does not look like an OpenRouter key (expected sk-or-v1-...)")
        return value


@router.post("/{room_id}/run")
async def start_run(
    room_id: str,
    body: RunRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> StreamingResponse:
    """Run the room, streaming each event as it happens."""
    room = await rooms_repo.get_room_with_agents(db, room_id)
    if room is None:
        raise NotFoundError(room_id)

    # Refused here rather than in the stream: a paused room is a state the
    # caller can see and change, so it should fail before the response starts
    # instead of arriving as an error event after being told the run began.
    if room.room.status is RoomStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This room is paused. Set it to active to start a run.",
        )

    transcript = await messages_repo.list_messages(db, room_id)

    settings = settings_for(request)
    limits = RunLimits.from_settings(settings)
    if body.max_turns is not None:
        limits = RunLimits(**{**limits.__dict__, "max_turns": body.max_turns})
    if body.spend_cap_usd is not None:
        limits = RunLimits(**{**limits.__dict__, "spend_cap_usd": body.spend_cap_usd})

    limiter = run_limiter()
    # Checked before the response starts, so a refusal is a clean 429 rather
    # than an error arriving mid-stream after the client has already been told
    # the run began.
    limiter.check(user.id)

    # Last of the refusals, because it is the only one that spends something:
    # a free run claimed for a request that was then turned away for another
    # reason would be gone for nothing.
    grant: TrialGrant | None = None
    if body.api_key is None:
        grant = await claim_trial(settings, user.id, RUN, room_id)
        # Our money, so our ceilings: whatever the request asked for, a free
        # run never gets more turns or more spending than the trial allows.
        limits = replace(
            limits,
            max_turns=min(limits.max_turns, settings.trial_run_max_turns),
            spend_cap_usd=min(limits.spend_cap_usd, settings.trial_run_spend_cap_usd),
        )

    llm = OpenRouterClient(
        grant.api_key if grant else body.api_key.get_secret_value(),
        model=grant.model if grant else body.model,
        app_url=settings.openrouter_app_url,
        app_title=settings.openrouter_app_title,
    )

    async def run_events():
        async for event in run_room(
            room,
            transcript,
            llm,
            SupabaseRunStore(db),
            limits=limits,
            user_id=user.id,
        ):
            if grant and isinstance(event, RunFinished) and _was_our_failure(event):
                # The stock explanations for these say "your key", which on a
                # free run is ours. Say what is true, and do not charge the
                # user a free run for it.
                event.result.detail = TRIAL_DOWN
                await release_trial(settings, grant.use_id)
            yield event

    async def events():
        try:
            async with limiter.hold(user.id):
                async for event in stream(run_events()):
                    yield event
        finally:
            # Releases the connection pool, and drops the only reference this
            # process holds to the caller's key.
            await llm.aclose()

    return _streaming(events())


def _was_our_failure(event: RunFinished) -> bool:
    """Whether a free run ended because our key could not pay for it."""
    return event.result.reason in (
        TerminationReason.KEY_REJECTED,
        TerminationReason.OUT_OF_CREDIT,
    )


def _streaming(events) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Nginx and several proxies buffer responses by default, which
            # would hold every event until the run ended and defeat the point.
            "X-Accel-Buffering": "no",
        },
    )
