"""Request-scoped dependencies."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends, Request
from supabase import AsyncClient

from ..auth import CurrentUser, access_token, current_user
from ..config import Settings, get_settings
from ..db import create_user_client
from ..repository import users as users_repo

_provisioned: set[str] = set()
"""Users this process has already confirmed have an application row.

Supabase Auth creates the login; nothing creates the matching row in
``public.users``, which every agent, room and usage record points at. Without
it a new account's first write fails a foreign key check. The row is upserted
on a user's first request to this process and remembered, so the cost is one
query per user per process rather than one per request.

A process restart forgets the set, which costs one harmless upsert per user.
"""


def settings_for(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


async def user_db(
    request: Request, user: CurrentUser = Depends(current_user)
) -> AsyncIterator[AsyncClient]:
    """A Supabase client acting as the caller.

    Built from the caller's own token, so every query it makes is subject to
    row-level security. This is what makes an endpoint unable to read another
    user's data even if its own filtering is wrong — the database refuses
    before the handler's logic matters.
    """
    client = await create_user_client(settings_for(request), access_token(request))
    try:
        if user.id not in _provisioned:
            # As the user rather than as the service role: row-level security
            # permits a user to create their own row and nobody else's, so this
            # cannot be used to provision an account the caller does not hold.
            await users_repo.ensure_user(client, user.id, user.email)
            _provisioned.add(user.id)
        yield client
    finally:
        await client.postgrest.aclose()
