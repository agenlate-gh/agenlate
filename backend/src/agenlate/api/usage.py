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

from datetime import datetime, timedelta, timezone

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
