"""Reads and writes against public.invite_codes.

Every function here takes a service-role client. The table has no policies and
no grants to browser roles, so a user client could not touch it at all — which
is the point: whether a code is valid is decided here, never in the browser.
"""

from __future__ import annotations

from datetime import datetime, timezone

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

    @property
    def is_claimed(self) -> bool:
        return self.claimed_at is not None


async def create_codes(client: AsyncClient, codes: list[str], label: str | None) -> list[InviteCode]:
    rows = await execute(
        client.table(TABLE).insert([{"code": code, "label": label} for code in codes]).select("*"),
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
    """Take a code if it is free. True if this call took it.

    One conditional update, so two people racing for the same code cannot both
    win: the database applies the ``claimed_at is null`` condition and the
    write together, and only one of them finds the row still free.
    """
    rows = await execute(
        client.table(TABLE)
        .update({"claimed_at": datetime.now(timezone.utc).isoformat()})
        .eq("code", code)
        .is_("claimed_at", "null")
        .select("code"),
        context="claim_invite_code",
    )
    return bool(rows)


async def release(client: AsyncClient, code: str) -> None:
    """Give a claimed code back, when the signup it was claimed for failed.

    Only a code with no owner yet: one already bound to an account is spent,
    and releasing it would let it be used twice.
    """
    await execute(
        client.table(TABLE)
        .update({"claimed_at": None})
        .eq("code", code)
        .is_("claimed_by", "null"),
        context="release_invite_code",
    )


async def bind(client: AsyncClient, code: str, user_id: str) -> None:
    """Record which account a claimed code created."""
    await execute(
        client.table(TABLE).update({"claimed_by": user_id}).eq("code", code),
        context="bind_invite_code",
    )
