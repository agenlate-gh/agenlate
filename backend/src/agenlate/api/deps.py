"""Request-scoped dependencies."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends, Request
from supabase import AsyncClient

from ..auth import CurrentUser, access_token, current_user
from ..config import Settings, get_settings
from ..db import create_user_client


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
        yield client
    finally:
        await client.postgrest.aclose()
