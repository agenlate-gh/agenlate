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

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, SecretStr, field_validator
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..db import NotFoundError
from ..llm.openrouter import OpenRouterClient
from ..orchestrator import run_room
from ..repository import messages as messages_repo
from ..repository import rooms as rooms_repo
from ..security import looks_like_openrouter_key
from ..store import SupabaseRunStore
from ..supervisor import RunLimits
from .deps import settings_for, user_db
from .sse import stream

router = APIRouter(prefix="/api/rooms", tags=["runs"])

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


class RunRequest(BaseModel):
    """What starting a run needs.

    The key is typed as a secret so that anything which stringifies this model
    — a validation error, a log line, an exception repr — masks it rather than
    printing it.
    """

    api_key: SecretStr = Field(description="The caller's own OpenRouter key.")
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)
    max_turns: int | None = Field(default=None, gt=0, le=50)
    spend_cap_usd: float | None = Field(default=None, gt=0, le=20)

    @field_validator("api_key")
    @classmethod
    def _shape(cls, value: SecretStr) -> SecretStr:
        """Reject an obviously malformed key before starting a run.

        The message never quotes the value: a validation error that echoed its
        input would put the key into the response body.
        """
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

    transcript = await messages_repo.list_messages(db, room_id)

    settings = settings_for(request)
    limits = RunLimits.from_settings(settings)
    if body.max_turns is not None:
        limits = RunLimits(**{**limits.__dict__, "max_turns": body.max_turns})
    if body.spend_cap_usd is not None:
        limits = RunLimits(**{**limits.__dict__, "spend_cap_usd": body.spend_cap_usd})

    llm = OpenRouterClient(
        body.api_key.get_secret_value(),
        model=body.model,
        app_url=settings.openrouter_app_url,
        app_title=settings.openrouter_app_title,
    )

    async def events():
        try:
            async for event in stream(
                run_room(
                    room,
                    transcript,
                    llm,
                    SupabaseRunStore(db),
                    limits=limits,
                    user_id=user.id,
                )
            ):
                yield event
        finally:
            # Releases the connection pool, and drops the only reference this
            # process holds to the caller's key.
            await llm.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Nginx and several proxies buffer responses by default, which
            # would hold every event until the run ended and defeat the point.
            "X-Accel-Buffering": "no",
        },
    )
