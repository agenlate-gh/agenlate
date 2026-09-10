"""Reads and writes against public.rooms and public.room_agents."""

from __future__ import annotations

from supabase import AsyncClient

from ..models import Agent, Room, RoomCreate, RoomUpdate, RoomWithAgents
from ._common import execute, fetch_many, fetch_one, require_one

TABLE = "rooms"
ROSTER_TABLE = "room_agents"


async def create_room(client: AsyncClient, creator_id: str, data: RoomCreate) -> Room:
    return await require_one(
        client.table(TABLE).insert({"creator_id": creator_id, **data.model_dump()}).select("*"),
        Room,
        context="create_room",
    )


async def get_room(client: AsyncClient, room_id: str) -> Room | None:
    return await fetch_one(
        client.table(TABLE).select("*").eq("id", room_id),
        Room,
        context=f"get_room({room_id})",
    )


async def list_rooms_for_user(client: AsyncClient, user_id: str) -> list[Room]:
    return await fetch_many(
        client.table(TABLE).select("*").eq("creator_id", user_id).order("created_at", desc=True),
        Room,
        context="list_rooms_for_user",
    )


async def update_room(client: AsyncClient, room_id: str, data: RoomUpdate) -> Room | None:
    changes = data.model_dump(exclude_none=True)
    if not changes:
        return await get_room(client, room_id)
    return await fetch_one(
        client.table(TABLE).update(changes).eq("id", room_id).select("*"),
        Room,
        context=f"update_room({room_id})",
    )


async def delete_room(client: AsyncClient, room_id: str) -> bool:
    rows = await execute(
        client.table(TABLE).delete().eq("id", room_id).select("id"),
        context=f"delete_room({room_id})",
    )
    return bool(rows)


async def add_agent_to_room(client: AsyncClient, room_id: str, agent_id: str) -> None:
    await execute(
        client.table(ROSTER_TABLE).upsert(
            {"room_id": room_id, "agent_id": agent_id},
            on_conflict="room_id,agent_id",
            ignore_duplicates=True,
        ),
        context="add_agent_to_room",
    )


async def remove_agent_from_room(client: AsyncClient, room_id: str, agent_id: str) -> bool:
    rows = await execute(
        client.table(ROSTER_TABLE)
        .delete()
        .eq("room_id", room_id)
        .eq("agent_id", agent_id)
        .select("room_id"),
        context="remove_agent_from_room",
    )
    return bool(rows)


async def get_room_with_agents(client: AsyncClient, room_id: str) -> RoomWithAgents | None:
    """Fetch a room and its roster in one request.

    The orchestrator needs both on every turn. Fetching the roster separately
    per agent is the beginning of an N+1 that would repeat once per turn, so
    the roster is embedded in the same query.
    """
    rows = await execute(
        client.table(TABLE).select("*, room_agents(agents(*))").eq("id", room_id),
        context=f"get_room_with_agents({room_id})",
    )
    if not rows:
        return None

    row = rows[0]
    roster = row.pop("room_agents", []) or []
    agents = [
        Agent.model_validate(entry["agents"])
        for entry in roster
        if entry.get("agents")
    ]
    agents.sort(key=lambda a: a.created_at)
    return RoomWithAgents(room=Room.model_validate(row), agents=agents)
