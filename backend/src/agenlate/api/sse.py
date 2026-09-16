"""Server-sent events.

The wire format is trivial; the two things that are not are keeping the
connection alive through a quiet stretch, and not cancelling the work that
produces the events while waiting for the next one.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from ..orchestrator import (
    AgentSpoke,
    AgentStarted,
    RunEvent,
    RunFinished,
    SupervisorDecided,
    UsageReported,
)
from .schemas import MessageOut

HEARTBEAT_SECONDS = 15.0
"""How long a silent connection may go before a comment is sent.

Proxies and load balancers drop connections they believe to be idle, and an
agent turn with several web searches can easily run past a minute without
producing an event.
"""


def encode(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"


def heartbeat() -> str:
    """An SSE comment. Clients ignore it; proxies see traffic."""
    return ": keepalive\n\n"


def to_payload(event: RunEvent) -> dict[str, Any]:
    """Shape an orchestrator event for the wire.

    Built from the API schemas rather than dumping internal objects, so the
    frontend's generated types describe these events too.
    """
    if isinstance(event, SupervisorDecided):
        return {
            "reasoning": event.decision.reasoning,
            "action": event.decision.action.value,
            "objective_status": event.decision.objective_status.value,
            "agent_id": event.decision.agent_id,
            "instruction": event.decision.instruction,
            "message_to_user": event.decision.message_to_user,
            "attempts": event.attempts,
            "message": MessageOut.of(event.message).model_dump(mode="json"),
        }
    if isinstance(event, AgentStarted):
        return {
            "agent_id": event.agent_id,
            "agent_name": event.agent_name,
            "instruction": event.instruction,
        }
    if isinstance(event, AgentSpoke):
        return {
            "agent_id": event.agent_id,
            "message": MessageOut.of(event.message).model_dump(mode="json"),
        }
    if isinstance(event, UsageReported):
        return {
            "call": {
                "prompt_tokens": event.usage.prompt_tokens,
                "completion_tokens": event.usage.completion_tokens,
                "cost_usd": event.usage.cost_usd,
            },
            "total": {
                "calls": event.total.calls,
                "prompt_tokens": event.total.prompt_tokens,
                "completion_tokens": event.total.completion_tokens,
                "cost_usd": event.total.cost_usd,
                "unpriced_calls": event.total.unpriced_calls,
                "has_unknown_cost": event.total.has_unknown_cost,
            },
        }
    if isinstance(event, RunFinished):
        result = event.result
        return {
            "reason": result.reason.value,
            "explanation": result.reason.describe(),
            "succeeded": result.succeeded,
            "turns": result.turns,
            "messages_added": result.messages_added,
            "final_message": result.final_message,
            "detail": result.detail,
            "usage": {
                "calls": result.usage.calls,
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "cost_usd": result.usage.cost_usd,
                "unpriced_calls": result.usage.unpriced_calls,
            },
        }
    return {}


async def stream(events: AsyncIterator[RunEvent]) -> AsyncIterator[str]:
    """Emit events as SSE, with heartbeats during quiet stretches.

    The obvious implementation — ``asyncio.wait_for`` around each step — is
    wrong: on timeout it cancels the awaited coroutine, which here is the run
    itself. A heartbeat would silently kill the work it was meant to keep alive.

    So the next event is pulled as a task and merely *waited on* with a
    timeout. A timeout leaves the task running and sends a comment.
    """
    iterator = events.__aiter__()
    pending = asyncio.ensure_future(iterator.__anext__())

    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_SECONDS)
            if not done:
                yield heartbeat()
                continue

            try:
                event = pending.result()
            except StopAsyncIteration:
                return

            yield encode(event.type, to_payload(event))
            pending = asyncio.ensure_future(iterator.__anext__())
    finally:
        # A client that disconnects leaves this generator closed mid-flight.
        # The in-flight step has to be cancelled or it keeps spending the
        # user's credit on a run nobody is watching.
        if not pending.done():
            pending.cancel()
        await iterator.aclose()  # type: ignore[attr-defined]
