"""Reads and writes against public.users."""

from __future__ import annotations

from supabase import AsyncClient

from ..models import User
from ._common import fetch_one, require_one

TABLE = "users"


async def get_user(client: AsyncClient, user_id: str) -> User | None:
    return await fetch_one(
        client.table(TABLE).select("*").eq("id", user_id),
        User,
        context=f"get_user({user_id})",
    )


async def ensure_user(client: AsyncClient, user_id: str, email: str) -> User:
    """Create the application row for an authenticated user if it is missing.

    Upsert rather than insert-if-absent: two requests can arrive together on a
    first login, and the loser of that race should not see an error.
    """
    return await require_one(
        client.table(TABLE).upsert(
            {"id": user_id, "email": email},
            on_conflict="id",
            ignore_duplicates=False,
        ).select("*"),
        User,
        context=f"ensure_user({user_id})",
    )
