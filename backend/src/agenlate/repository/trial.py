"""Reads and writes against public.trial_uses.

Every function here takes a service-role client. The table has no policies and
no grants to browser roles: how many free runs an account has left is decided
here, never in the browser.
"""

from __future__ import annotations

from pydantic import BaseModel
from supabase import AsyncClient

from ._common import execute

TABLE = "trial_uses"


class Claim(BaseModel):
    outcome: str
    """``claimed``, ``user_limit`` or ``total_limit``."""

    remaining: int = 0
    use_id: str | None = None

    @property
    def claimed(self) -> bool:
        return self.outcome == "claimed"


async def claim(
    client: AsyncClient,
    *,
    user_id: str,
    kind: str,
    room_id: str | None,
    user_limit: int,
    total_limit: int,
) -> Claim:
    """Take one use if both limits allow it.

    A database function rather than a count followed by an insert: the check
    and the write happen under one lock, so two requests racing for the last
    place cannot both get it.
    """
    rows = await execute(
        client.rpc(
            "claim_trial_use",
            {
                "p_user_id": user_id,
                "p_kind": kind,
                "p_room_id": room_id,
                "p_user_limit": user_limit,
                "p_total_limit": total_limit,
            },
        ),
        context="claim_trial_use",
    )
    return Claim.model_validate(rows[0])


async def release(client: AsyncClient, use_id: str) -> None:
    """Give a use back, when what it was claimed for never happened."""
    await execute(
        client.table(TABLE).delete().eq("id", use_id),
        context="release_trial_use",
    )


async def used(client: AsyncClient, user_id: str, kind: str) -> int:
    """How many uses of this kind an account has taken."""
    rows = await execute(
        client.table(TABLE).select("id").eq("user_id", user_id).eq("kind", kind),
        context="count_trial_uses",
    )
    return len(rows)
