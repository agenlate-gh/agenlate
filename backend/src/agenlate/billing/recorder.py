"""Writing what each request cost.

Recording is not deferred even though billing is. Phase 1 metrics — token
volume, cost per active user, how much is moving through the platform — are
what the pre-seed round is meant to be argued from, and they can only be
computed from rows that were written while the Beta was running. There is no
retrofitting this later.

The provider's figures are stored exactly as reported. The margin is applied
downstream, at read time, and never mutates a stored row: once a recorded cost
has been marked up in place, there is no way to tell what the provider actually
charged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from supabase import AsyncClient

from ..llm import Usage
from ..models import UsageEvent, UsageEventCreate
from ..repository import usage as usage_repo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageContext:
    """Who and what a request belongs to."""

    user_id: str
    model: str
    room_id: str | None = None
    message_id: str | None = None
    generation_id: str | None = None


def to_event(usage: Usage, context: UsageContext) -> UsageEventCreate:
    """Turn provider figures into a ledger row, untouched."""
    return UsageEventCreate(
        user_id=context.user_id,
        room_id=context.room_id,
        message_id=context.message_id,
        model=context.model or "unknown",
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cost_usd=usage.cost_usd,
        server_tool_calls=usage.server_tool_calls,
        provider_generation_id=context.generation_id,
    )


async def record(
    client: AsyncClient, usage: Usage, context: UsageContext
) -> UsageEvent:
    """Write one usage row.

    An unpriced request is stored with a null cost and flagged, never as zero.
    Zero is a claim that the request was free; null is the truth, which is that
    nobody said. A database check constraint enforces the same rule, so this is
    a clear error message rather than the guarantee.
    """
    event = to_event(usage, context)

    if not event.is_priced:
        # Worth a warning rather than a silent row: a provider that stops
        # reporting cost disables the spend cap, and the run guard will
        # eventually stop the run over it.
        logger.warning(
            "unpriced request recorded",
            extra={
                "model": event.model,
                "room_id": event.room_id,
                "prompt_tokens": event.prompt_tokens,
                "completion_tokens": event.completion_tokens,
                "server_tool_calls": event.server_tool_calls,
            },
        )

    return await usage_repo.record_usage_event(client, event)


@dataclass(frozen=True)
class UsageSummary:
    """Aggregated usage, as the Phase 1 metrics need it."""

    total_requests: int = 0
    priced_requests: int = 0
    unpriced_requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    server_tool_calls: int = 0
    rooms_touched: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None

    @property
    def has_unpriced(self) -> bool:
        return self.unpriced_requests > 0

    @property
    def coverage(self) -> float:
        """Share of requests whose cost is actually known.

        Below one, ``cost_usd`` is a floor rather than a total — which matters
        before anyone quotes it as revenue.
        """
        if self.total_requests == 0:
            return 1.0
        return self.priced_requests / self.total_requests


async def summarise(
    client: AsyncClient,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    room_id: str | None = None,
) -> UsageSummary:
    """Aggregate the caller's usage.

    Computed in the database rather than by fetching rows and adding them up:
    this is meant to answer questions about volume, and by the time the volume
    is interesting it will not fit through the wire.
    """
    response = await client.rpc(
        "usage_summary",
        {
            "p_from": since.isoformat() if since else None,
            "p_to": until.isoformat() if until else None,
            "p_room_id": room_id,
        },
    ).execute()

    rows = response.data or []
    if not rows:
        return UsageSummary()

    row = rows[0]
    return UsageSummary(
        total_requests=int(row.get("total_requests") or 0),
        priced_requests=int(row.get("priced_requests") or 0),
        unpriced_requests=int(row.get("unpriced_requests") or 0),
        prompt_tokens=int(row.get("prompt_tokens") or 0),
        completion_tokens=int(row.get("completion_tokens") or 0),
        total_tokens=int(row.get("total_tokens") or 0),
        cost_usd=float(row.get("cost_usd") or 0.0),
        server_tool_calls=int(row.get("server_tool_calls") or 0),
        rooms_touched=int(row.get("rooms_touched") or 0),
        first_at=_parse_time(row.get("first_at")),
        last_at=_parse_time(row.get("last_at")),
    )


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
