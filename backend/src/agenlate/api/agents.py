"""Agent endpoints.

Every handler is scoped by the caller's own database client, so row-level
security filters before any of this code runs. A missing row and someone
else's row are therefore the same case, and both answer 404: confirming that a
row exists but belongs to another user leaks its existence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..db import NotFoundError
from ..models import AgentCreate, AgentUpdate
from ..repository import agents as repo
from .deps import user_db
from .schemas import AgentIn, AgentOut, AgentPatch

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
async def list_agents(
    user: CurrentUser = Depends(current_user), db: AsyncClient = Depends(user_db)
) -> list[AgentOut]:
    return [AgentOut.of(a) for a in await repo.list_agents_for_user(db, user.id)]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentIn,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> AgentOut:
    agent = await repo.create_agent(
        db,
        user.id,
        AgentCreate(
            name=body.name,
            role=body.role,
            system_prompt=body.system_prompt,
            enabled_tools=body.enabled_tools,
        ),
    )
    return AgentOut.of(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> AgentOut:
    agent = await repo.get_agent(db, agent_id)
    if agent is None:
        raise NotFoundError(agent_id)
    return AgentOut.of(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str,
    body: AgentPatch,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> AgentOut:
    agent = await repo.update_agent(
        db,
        agent_id,
        AgentUpdate(
            name=body.name,
            role=body.role,
            system_prompt=body.system_prompt,
            enabled_tools=body.enabled_tools,
        ),
    )
    if agent is None:
        raise NotFoundError(agent_id)
    return AgentOut.of(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> None:
    if not await repo.delete_agent(db, agent_id):
        raise NotFoundError(agent_id)
