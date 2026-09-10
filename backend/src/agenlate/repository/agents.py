"""Reads and writes against public.agents."""

from __future__ import annotations

from supabase import AsyncClient

from ..models import Agent, AgentCreate, AgentUpdate
from ._common import execute, fetch_many, fetch_one, require_one

TABLE = "agents"


async def create_agent(client: AsyncClient, creator_id: str, data: AgentCreate) -> Agent:
    return await require_one(
        client.table(TABLE).insert({"creator_id": creator_id, **data.model_dump()}).select("*"),
        Agent,
        context="create_agent",
    )


async def get_agent(client: AsyncClient, agent_id: str) -> Agent | None:
    return await fetch_one(
        client.table(TABLE).select("*").eq("id", agent_id),
        Agent,
        context=f"get_agent({agent_id})",
    )


async def list_agents_for_user(client: AsyncClient, user_id: str) -> list[Agent]:
    return await fetch_many(
        client.table(TABLE).select("*").eq("creator_id", user_id).order("created_at"),
        Agent,
        context="list_agents_for_user",
    )


async def update_agent(client: AsyncClient, agent_id: str, data: AgentUpdate) -> Agent | None:
    changes = data.model_dump(exclude_none=True)
    if not changes:
        return await get_agent(client, agent_id)
    return await fetch_one(
        client.table(TABLE).update(changes).eq("id", agent_id).select("*"),
        Agent,
        context=f"update_agent({agent_id})",
    )


async def delete_agent(client: AsyncClient, agent_id: str) -> bool:
    """Returns whether a row was actually removed.

    Under RLS a delete against someone else's row affects nothing rather than
    failing, so the row count is the only signal the caller gets.
    """
    rows = await execute(
        client.table(TABLE).delete().eq("id", agent_id).select("id"),
        context=f"delete_agent({agent_id})",
    )
    return bool(rows)
