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
