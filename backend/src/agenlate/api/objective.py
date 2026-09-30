"""The objective-writing conversation, over HTTP.

Stateless, like the agent builder: the client sends the conversation and gets
a draft back, and nothing is saved until the user accepts it into the form.
Not scoped to a room, because it runs before the room exists — writing the
objective is part of creating one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr, field_validator

from ..auth import CurrentUser, current_user
from ..llm.openrouter import OpenRouterClient
from ..models import OBJECTIVE_MAX, ROOM_NAME_MAX
from ..objective import ObjectiveError, refine_objective
from ..security import looks_like_openrouter_key
from .builder import BUILDER_DEFAULT_MODEL, MAX_CONVERSATION_TURNS, BuilderMessage
from .deps import settings_for

router = APIRouter(prefix="/api/rooms", tags=["objective"])


class ObjectiveRequest(BaseModel):
    api_key: SecretStr
    conversation: list[BuilderMessage] = Field(
        default_factory=list, max_length=MAX_CONVERSATION_TURNS
    )
    model: str = Field(default=BUILDER_DEFAULT_MODEL, min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=ROOM_NAME_MAX)
    objective: str | None = Field(
        default=None,
        max_length=OBJECTIVE_MAX,
        description="What the form holds now, so a revision keeps what the user did not change.",
    )

    @field_validator("api_key")
    @classmethod
    def _shape(cls, value: SecretStr) -> SecretStr:
        if not looks_like_openrouter_key(value.get_secret_value()):
            raise ValueError("does not look like an OpenRouter key (expected sk-or-v1-...)")
        return value


class ObjectiveResponse(BaseModel):
    reply: str
    objective: str | None
    name: str | None = Field(
        default=None, description="A suggested room name, only when the room had none."
    )
    needs_answer: bool
    cost_usd: float | None = None


@router.post("/objective-draft", response_model=ObjectiveResponse)
async def draft_objective(
    body: ObjectiveRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
) -> ObjectiveResponse:
    """Take one turn of the conversation that writes a room's objective."""
    settings = settings_for(request)
    llm = OpenRouterClient(
        body.api_key.get_secret_value(),
        model=body.model,
        app_url=settings.openrouter_app_url,
        app_title=settings.openrouter_app_title,
    )

    try:
        turn = await refine_objective(
            llm,
            name=body.name,
            objective=body.objective,
            conversation=[m.model_dump() for m in body.conversation],
        )
    except ObjectiveError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The model did not return a usable reply. "
                "Try again, or reword what you need."
            ),
        ) from None
    finally:
        await llm.aclose()

    return ObjectiveResponse(
        reply=turn.reply.reply,
        objective=turn.reply.objective,
        name=turn.reply.name,
        needs_answer=turn.reply.needs_answer,
        cost_usd=turn.usage.cost_usd,
    )
