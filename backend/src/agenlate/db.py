"""Supabase client construction.

Two ways to reach the database, and the difference matters:

``user_client``     carries the caller's JWT, so row-level security applies and
                    the database enforces isolation. This is the default and
                    should be what almost every request uses.

``service_client``  holds the service-role key, which has BYPASSRLS. Nothing
                    protects one user's data from another here except the code
                    you are about to write. Every call site must justify itself.

Clients are constructed per request and injected. There is no module-level
client, because a shared client would have to carry a single identity and that
identity would inevitably become the service role.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from supabase import AsyncClient, create_async_client

from .config import Settings


class RepositoryError(RuntimeError):
    """A database operation failed."""


class DatabaseUnavailable(RepositoryError):
    """The database could not be reached at all.

    Separate from a query the database rejected: nothing is wrong with the
    request, and trying again in a moment is the right response — which is
    what the API tells the client, rather than a generic failure.
    """


class NotFoundError(RepositoryError):
    """The requested row does not exist, or row-level security hides it.

    These two cases are deliberately indistinguishable. Telling a caller that a
    row exists but belongs to someone else leaks its existence.
    """


async def create_user_client(settings: Settings, access_token: str) -> AsyncClient:
    """Client acting as the authenticated user, subject to RLS."""
    client = await create_async_client(
        settings.supabase_url,
        settings.supabase_anon_key.get_secret_value(),
    )
    # PostgREST reads identity from this bearer token; auth.uid() in every
    # policy resolves from it.
    client.postgrest.auth(access_token)
    return client


async def create_service_client(settings: Settings) -> AsyncClient:
    """Client with the service-role key. Bypasses row-level security entirely.

    Only for operations that genuinely cannot run as a user — and each one
    should say why at its call site.
    """
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
    )


@asynccontextmanager
async def user_session(settings: Settings, access_token: str) -> AsyncIterator[AsyncClient]:
    """Scope a user client to a block."""
    client = await create_user_client(settings, access_token)
    try:
        yield client
    finally:
        # supabase-py holds an httpx client per instance; releasing it keeps
        # long-lived processes from accumulating connections per request.
        await client.postgrest.aclose()
