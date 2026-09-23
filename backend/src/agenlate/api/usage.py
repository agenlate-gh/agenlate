"""What a user has spent, and what the Beta is actually costing.

The metric this deliberately does not lead with is token volume. Measured on
real runs, the same room cost $0.000179 with web search switched off and
$0.007285 with it on — a factor of forty, almost none of which is tokens. Two
users with identical token counts can differ by that much, so token volume
answers a question nobody has.

What matters is how much of the spending came from calls that could reach the
web. That is reported separately here, so the split is visible rather than
inferred.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..repository._common import execute
from .deps import user_db

router = APIRouter(prefix="/api/usage", tags=["usage"])


class UsageSummary(BaseModel):
    """A user's own spending over a window."""

    since: datetime
    rooms: int = Field(description="Rooms that saw activity in this window.")
    requests: int
    prompt_tokens: int
    completion_tokens: int

    cost_usd: float = Field(description="What the provider reported, summed.")
    unpriced_requests: int = Field(
        description=(
            "Requests the provider did not price. The cost above is a floor "
            "rather than a total when this is above zero."
        )
    )
    cost_is_complete: bool

    tool_enabled_requests: int = Field(
        description="Requests that could reach the web."
    )
    tool_enabled_cost_usd: float = Field(
        description=(
            "Reported cost of those requests. A web search costs roughly forty "
            "times the tokens of a room, so this is where spending actually "
            "comes from."
        )
    )


class DailyUsage(BaseModel):
    """One day's spending, for the chart on the billing screen."""

    day: date
    requests: int
    cost_usd: float


@router.get("/daily", response_model=list[DailyUsage])
async def usage_daily(
    days: int = Query(default=30, ge=1, le=365),
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> list[DailyUsage]:
    """Spending per day, oldest first, with quiet days included as zero.

    The zeroes matter. A chart that plots only the days with activity draws a
    continuous line through a fortnight of nothing, which reads as steady
    spending rather than as a gap.

    Days are UTC, matching how ``created_at`` is stored. A user in another
    timezone sees a boundary that is not their midnight; correcting that needs
    their offset, which is worth asking for only once anyone is reconciling
    these numbers against an invoice.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await execute(
        db.table("usage_events")
        .select("created_at,cost_usd,is_priced")
        .eq("user_id", user.id)
        .gte("created_at", since.isoformat()),
        context="usage_daily",
    )

    totals: dict[date, tuple[int, float]] = {}
    for row in rows:
        if not row.get("created_at"):
            continue
        day = datetime.fromisoformat(row["created_at"]).astimezone(timezone.utc).date()
        requests, cost = totals.get(day, (0, 0.0))
        priced = row.get("is_priced") and row.get("cost_usd") is not None
        totals[day] = (requests + 1, cost + (float(row["cost_usd"]) if priced else 0.0))

    start = since.date()
    today = datetime.now(timezone.utc).date()
    span = (today - start).days

    return [
        DailyUsage(
            day=start + timedelta(days=offset),
            requests=totals.get(start + timedelta(days=offset), (0, 0.0))[0],
            cost_usd=round(totals.get(start + timedelta(days=offset), (0, 0.0))[1], 6),
        )
        for offset in range(span + 1)
    ]


class RoomUsage(BaseModel):
    """What one room has cost its owner.

    The lobby shows this on every card, so it is one request for every room
    rather than one per room. Rooms with no recorded usage are absent, which
    the caller reads as zero — storing a zero row for a room nobody has run
    would be inventing a fact.
    """

    room_id: str
    requests: int
    cost_usd: float
    unpriced_requests: int
    cost_is_complete: bool
    last_active_at: datetime | None


@router.get("/rooms", response_model=list[RoomUsage])
async def usage_by_room(
    days: int = Query(default=30, ge=1, le=365),
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> list[RoomUsage]:
    """Per-room spending over a window, most expensive first."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await execute(
        db.table("usage_events")
        .select("room_id,cost_usd,is_priced,created_at")
        .eq("user_id", user.id)
        .gte("created_at", since.isoformat()),
        context="usage_by_room",
    )

    by_room: dict[str, list[dict]] = {}
    for row in rows:
        room_id = row.get("room_id")
        if room_id:
            by_room.setdefault(room_id, []).append(row)

    summaries = [
        RoomUsage(
            room_id=room_id,
            requests=len(events),
            cost_usd=round(
                sum(
                    float(e["cost_usd"])
                    for e in events
                    if e.get("is_priced") and e.get("cost_usd") is not None
                ),
                6,
            ),
            unpriced_requests=sum(1 for e in events if not e.get("is_priced")),
            cost_is_complete=all(e.get("is_priced") for e in events),
            last_active_at=max(
                (
                    datetime.fromisoformat(e["created_at"])
                    for e in events
                    if e.get("created_at")
                ),
                default=None,
            ),
        )
        for room_id, events in by_room.items()
    ]
    summaries.sort(key=lambda s: s.cost_usd, reverse=True)
    return summaries


class UsageEventOut(BaseModel):
    """One provider call, as the audit log shows it."""

    id: str
    created_at: datetime
    model: str
    room_id: str | None
    room_name: str | None = Field(
        default=None,
        description="Null when the room has since been deleted; the spending still happened.",
    )
    emitter_name: str | None = Field(
        default=None, description="Who was speaking when this was spent."
    )
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None = Field(
        default=None, description="Null when the provider did not price the call."
    )


@router.get("/events", response_model=list[UsageEventOut])
async def usage_events(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> list[UsageEventOut]:
    """This caller's most recent provider calls, newest first.

    The room name and the speaker are embedded rather than resolved by the
    client, which would otherwise issue a request per row. Both can be null:
    usage deliberately outlives the room and the message it came from, because
    deleting a room must not erase the record of money already spent.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await execute(
        db.table("usage_events")
        .select(
            "id,created_at,model,room_id,prompt_tokens,completion_tokens,cost_usd,"
            "rooms(name),messages(emitter_name)"
        )
        .eq("user_id", user.id)
        .gte("created_at", since.isoformat())
        .order("created_at", desc=True)
        .limit(limit),
        context="usage_events",
    )

    return [
        UsageEventOut(
            id=row["id"],
            created_at=row["created_at"],
            model=row["model"],
            room_id=row.get("room_id"),
            room_name=(row.get("rooms") or {}).get("name"),
            emitter_name=(row.get("messages") or {}).get("emitter_name"),
            prompt_tokens=int(row.get("prompt_tokens") or 0),
            completion_tokens=int(row.get("completion_tokens") or 0),
            cost_usd=float(row["cost_usd"]) if row.get("cost_usd") is not None else None,
        )
        for row in rows
    ]


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    days: int = Query(default=30, ge=1, le=365),
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> UsageSummary:
    """Summarise this caller's usage.

    Aggregated in Python rather than SQL: the row counts here are small — one
    per provider request per user — and a database function would be a second
    place for the definition of "cost" to live and drift.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await execute(
        db.table("usage_events")
        .select("room_id,prompt_tokens,completion_tokens,cost_usd,is_priced,server_tool_calls,model")
        .eq("user_id", user.id)
        .gte("created_at", since.isoformat()),
        context="usage_summary",
    )

    prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in rows)
    completion_tokens = sum(int(r.get("completion_tokens") or 0) for r in rows)
    priced = [r for r in rows if r.get("is_priced") and r.get("cost_usd") is not None]
    cost = sum(float(r["cost_usd"]) for r in priced)
    unpriced = sum(1 for r in rows if not r.get("is_priced"))

    # server_tool_calls is best effort: OpenRouter frequently reports no tool
    # counts even when a search ran, so a zero here does not mean no tools.
    with_tools = [r for r in rows if int(r.get("server_tool_calls") or 0) > 0]
    tool_cost = sum(
        float(r["cost_usd"])
        for r in with_tools
        if r.get("is_priced") and r.get("cost_usd") is not None
    )

    return UsageSummary(
        since=since,
        rooms=len({r["room_id"] for r in rows if r.get("room_id")}),
        requests=len(rows),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost, 6),
        unpriced_requests=unpriced,
        cost_is_complete=unpriced == 0,
        tool_enabled_requests=len(with_tools),
        tool_enabled_cost_usd=round(tool_cost, 6),
    )
