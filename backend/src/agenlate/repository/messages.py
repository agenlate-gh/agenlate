"""Reads and writes against public.messages."""

from __future__ import annotations

from supabase import AsyncClient

from ..models import Message, MessageCreate
from ._common import execute, fetch_many, require_one

TABLE = "messages"


async def append_message(client: AsyncClient, data: MessageCreate) -> Message:
    payload = data.model_dump()
    payload["emitter"] = data.emitter.value
    return await require_one(
        client.table(TABLE).insert(payload).select("*"),
        Message,
        context="append_message",
    )


async def list_messages(
    client: AsyncClient,
    room_id: str,
    *,
    after_seq: int | None = None,
    limit: int | None = None,
) -> list[Message]:
    """Return a room's transcript in order.

    Ordered by seq, never created_at: a supervisor decision and the agent
    message it triggers can share a timestamp, and replaying them in the wrong
    order misstates who acted when.
    """
    query = client.table(TABLE).select("*").eq("room_id", room_id)
    if after_seq is not None:
        query = query.gt("seq", after_seq)
    query = query.order("seq")
    if limit is not None:
        query = query.limit(limit)
    return await fetch_many(query, Message, context="list_messages")


async def count_messages(client: AsyncClient, room_id: str) -> int:
    rows = await execute(
        client.table(TABLE).select("id").eq("room_id", room_id),
        context="count_messages",
    )
    return len(rows)
