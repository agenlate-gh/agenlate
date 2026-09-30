"""Reads and writes against public.waitlist. Service-role client only.

The table has no policies and no grants to browser roles, so these functions
cannot work with a user client — which is the intent. The list of people who
asked to join is personal data that nothing in the browser needs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from supabase import AsyncClient

from ._common import execute

TABLE = "waitlist"


class WaitlistEntry(BaseModel):
    id: int
    email: str
    source: str
    created_at: datetime
    invited_at: datetime | None = None


async def join(client: AsyncClient, email: str, source: str) -> None:
    """Add an email, or do nothing if it is already there.

    Asking twice is the same as asking once. ``ignore_duplicates`` makes the
    second request a no-op rather than an error, so the caller cannot tell the
    two cases apart — and so neither can anyone probing whether an address is
    on the list.
    """
    await execute(
        client.table(TABLE).upsert(
            {"email": email, "source": source},
            on_conflict="email",
            ignore_duplicates=True,
        ),
        context="join_waitlist",
    )


async def list_entries(client: AsyncClient, *, waiting_only: bool = False) -> list[WaitlistEntry]:
    query = client.table(TABLE).select("*").order("created_at")
    if waiting_only:
        query = query.is_("invited_at", "null")
    rows = await execute(query, context="list_waitlist")
    return [WaitlistEntry.model_validate(row) for row in rows]
