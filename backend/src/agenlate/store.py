"""The Supabase-backed RunStore.

Adapts the repository to the protocol the orchestrator depends on. Thin by
design: the loop is tested against an in-memory store, and anything with real
behaviour hiding in here would be behaviour those tests never see.
"""

from __future__ import annotations

from supabase import AsyncClient

from .billing.recorder import UsageContext
from .billing.recorder import record as record_usage
from .llm import Usage
from .models import Message, MessageCreate, UsageEventCreate
from .repository import messages as messages_repo
from .repository import usage as usage_repo


class SupabaseRunStore:
    """Persists a run through the caller's own client, so RLS applies."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def append(self, message: MessageCreate) -> Message:
        return await messages_repo.append_message(self._client, message)

    async def record_usage(self, event: UsageEventCreate) -> None:
        await usage_repo.record_usage_event(self._client, event)

    async def record(self, usage: Usage, context: UsageContext) -> None:
        """Record straight from provider figures, with the unpriced warning."""
        await record_usage(self._client, usage, context)


class InMemoryRunStore:
    """A RunStore that keeps everything in the process.

    Used by the command line, which runs a room without an account. Nothing
    here survives the process, which is the point: the CLI exists to exercise
    orchestration, not to accumulate state.
    """

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.messages: list[Message] = []
        self.usage: list[UsageEventCreate] = []

    async def append(self, message: MessageCreate) -> Message:
        from datetime import datetime, timezone

        stored = Message(
            id=f"local-{len(self.messages) + 1}",
            seq=len(self.messages) + 1,
            room_id=message.room_id,
            emitter=message.emitter,
            emitter_name=message.emitter_name,
            content=message.content,
            created_at=datetime.now(timezone.utc),
        )
        self.messages.append(stored)
        return stored

    async def record_usage(self, event: UsageEventCreate) -> None:
        self.usage.append(event)
