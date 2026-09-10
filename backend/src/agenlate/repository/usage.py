"""Reads and writes against public.usage_events.

Append-only. There is deliberately no update or delete function here, and the
database withholds those grants from authenticated as well: a ledger a user can
rewrite is not a ledger.
"""

from __future__ import annotations

from supabase import AsyncClient

from ..models import UsageEvent, UsageEventCreate
from ._common import fetch_many, require_one

TABLE = "usage_events"


async def record_usage_event(client: AsyncClient, data: UsageEventCreate) -> UsageEvent:
    """Write one usage row.

    ``is_priced`` is derived from whether a cost was reported rather than
    passed in, so a request the provider did not price is stored with a null
    cost and never as zero. A check constraint enforces the same rule at the
    database, which is what makes it a guarantee rather than a convention.
    """
    payload = data.model_dump()
    payload["is_priced"] = data.is_priced
    return await require_one(
        client.table(TABLE).insert(payload).select("*"),
        UsageEvent,
        context="record_usage_event",
    )


async def list_usage_for_user(
    client: AsyncClient, user_id: str, *, limit: int = 100
) -> list[UsageEvent]:
    return await fetch_many(
        client.table(TABLE)
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit),
        UsageEvent,
        context="list_usage_for_user",
    )


async def list_usage_for_room(client: AsyncClient, room_id: str) -> list[UsageEvent]:
    return await fetch_many(
        client.table(TABLE).select("*").eq("room_id", room_id).order("created_at"),
        UsageEvent,
        context="list_usage_for_room",
    )
