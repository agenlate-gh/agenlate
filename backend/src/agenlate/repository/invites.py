"""Reads and writes against public.invite_codes.

Every function here takes a service-role client. The table has no policies and
no grants to browser roles, so a user client could not touch it at all — which
is the point: whether a code is valid is decided here, never in the browser.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from supabase import AsyncClient

from ._common import execute

TABLE = "invite_codes"


class InviteCode(BaseModel):
    code: str
    label: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    max_uses: int = 1
    use_count: int = 0

    @property
    def is_claimed(self) -> bool:
        """Whether the code has no uses left."""
        return self.use_count >= self.max_uses


async def create_codes(
    client: AsyncClient, codes: list[str], label: str | None, max_uses: int = 1
) -> list[InviteCode]:
    rows = await execute(
        client.table(TABLE)
        .insert([{"code": code, "label": label, "max_uses": max_uses} for code in codes])
        .select("*"),
        context="create_invite_codes",
    )
    return [InviteCode.model_validate(row) for row in rows]


async def list_codes(client: AsyncClient) -> list[InviteCode]:
    rows = await execute(
        client.table(TABLE).select("*").order("created_at", desc=True),
        context="list_invite_codes",
    )
    return [InviteCode.model_validate(row) for row in rows]


async def claim(client: AsyncClient, code: str) -> bool:
    """Take one use of a code, if it has one left. True if this call took it.

    A database function rather than a read and a write: the check and the
    increment happen in one statement, so two people racing for the last use
    of a code cannot both get it.
    """
    rows = await execute(
        client.rpc("claim_invite_code", {"p_code": code}),
        context="claim_invite_code",
    )
    return bool(rows)


async def release(client: AsyncClient, code: str) -> None:
    """Give back a use taken for a signup that then failed."""
    await execute(
        client.rpc("release_invite_code", {"p_code": code}),
        context="release_invite_code",
    )


async def bind(client: AsyncClient, code: str, user_id: str) -> None:
    """Record the first account a code created.

    Only the first: a shared code creates many accounts, and each of them
    records its own code in its app metadata, which is where a channel's
    sign-ups are counted from.
    """
    await execute(
        client.table(TABLE)
        .update({"claimed_by": user_id})
        .eq("code", code)
        .is_("claimed_by", "null"),
        context="bind_invite_code",
    )
