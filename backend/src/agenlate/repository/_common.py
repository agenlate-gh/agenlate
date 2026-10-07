"""Shared helpers for the repository layer.

Thin by intention. The repository maps rows to models and nothing else — no
business rules, no orchestration, no implicit writes.
"""

from __future__ import annotations

from typing import Any, TypeVar

import httpx
from postgrest.exceptions import APIError
from pydantic import BaseModel

from ..db import DatabaseUnavailable, NotFoundError, RepositoryError

M = TypeVar("M", bound=BaseModel)


async def execute(query: Any, *, context: str) -> list[dict]:
    """Run a PostgREST query and return its rows.

    Translates provider errors into ``RepositoryError`` so callers above this
    layer never import postgrest.
    """
    try:
        response = await query.execute()
    except APIError as exc:
        raise RepositoryError(f"{context}: {exc.message}") from exc
    except httpx.HTTPError as exc:
        # The request never got an answer: a dropped connection, a timeout, a
        # failed TLS handshake. Left alone this surfaced as an unhandled crash
        # with a traceback for a body. `from None` because the chained httpx
        # error carries the request, and the request carries the user's token.
        raise DatabaseUnavailable(f"{context}: {type(exc).__name__}") from None
    return response.data or []


async def fetch_one(query: Any, model: type[M], *, context: str) -> M | None:
    rows = await execute(query, context=context)
    return model.model_validate(rows[0]) if rows else None


async def fetch_many(query: Any, model: type[M], *, context: str) -> list[M]:
    rows = await execute(query, context=context)
    return [model.model_validate(row) for row in rows]


async def require_one(query: Any, model: type[M], *, context: str) -> M:
    """Fetch exactly one row, raising when it is absent or invisible."""
    result = await fetch_one(query, model, context=context)
    if result is None:
        raise NotFoundError(context)
    return result
