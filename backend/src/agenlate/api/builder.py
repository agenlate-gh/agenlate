"""The agent-building conversation, over HTTP.

Stateless on purpose: the client sends the conversation each time and receives
a draft back. Nothing is saved until the user accepts it and the client PATCHes
the agent — so what ends up as the agent's instructions is always something a
person chose, not something written on their behalf while they were reading.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr, field_validator
from supabase import AsyncClient

from ..agents.builder import SYSTEM_PROMPT_MAX, BuilderError, refine_agent
from ..auth import CurrentUser, current_user
from ..db import NotFoundError
from ..llm.openrouter import OpenRouterClient
from ..models import NAME_MAX, ROLE_MAX
from ..repository import agents as agents_repo
from ..security import looks_like_openrouter_key
from .deps import settings_for, user_db

router = APIRouter(prefix="/api/agents", tags=["builder"])

BUILDER_DEFAULT_MODEL = "qwen/qwen3.7-flash"
MAX_CONVERSATION_TURNS = 40


class BuilderMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class BuilderRequest(BaseModel):
    api_key: SecretStr
    conversation: list[BuilderMessage] = Field(default_factory=list, max_length=MAX_CONVERSATION_TURNS)
    model: str = Field(default=BUILDER_DEFAULT_MODEL, min_length=1, max_length=200)

    # Sent by the client so an agent can be designed before it is saved. The
    # stored agent is used when these are absent.
    name: str | None = Field(default=None, max_length=NAME_MAX)
    role: str | None = Field(default=None, max_length=ROLE_MAX)
    instructions: str | None = Field(default=None, max_length=SYSTEM_PROMPT_MAX)

    @field_validator("api_key")
    @classmethod
    def _shape(cls, value: SecretStr) -> SecretStr:
        if not looks_like_openrouter_key(value.get_secret_value()):
            raise ValueError("does not look like an OpenRouter key (expected sk-or-v1-...)")
        return value


class BuilderResponse(BaseModel):
    reply: str
    instructions: str | None
    needs_answer: bool
    cost_usd: float | None = None


@router.post("/{agent_id}/builder", response_model=BuilderResponse)
async def build_agent(
    agent_id: str,
    body: BuilderRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> BuilderResponse:
    """Take one turn of the conversation that writes an agent's instructions."""
    agent = await agents_repo.get_agent(db, agent_id)
    if agent is None:
        raise NotFoundError(agent_id)

    settings = settings_for(request)
    llm = OpenRouterClient(
        body.api_key.get_secret_value(),
        model=body.model,
        app_url=settings.openrouter_app_url,
        app_title=settings.openrouter_app_title,
    )

    try:
        turn = await refine_agent(
            llm,
            name=body.name if body.name is not None else agent.name,
            role=body.role if body.role is not None else agent.role,
            # An empty string means "start over", which is different from
            # absent meaning "use what is stored".
            instructions=(
                body.instructions if body.instructions is not None else agent.system_prompt
            ),
            conversation=[m.model_dump() for m in body.conversation],
        )
    except BuilderError:
        # Not a 404 — the agent exists. The model simply failed to produce a
        # usable reply, which the user fixes by trying again or rewording.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The model did not return a usable reply. "
                "Try again, or reword what you need."
            ),
        ) from None
    finally:
        await llm.aclose()

    return BuilderResponse(
        reply=turn.reply.reply,
        instructions=turn.reply.instructions,
        needs_answer=turn.reply.needs_answer,
        cost_usd=turn.usage.cost_usd,
    )
