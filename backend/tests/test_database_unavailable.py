"""What happens when the database cannot be reached.

Seen for real during testing on a poor connection: the request hung for a
minute and then crashed with a raw traceback as its body.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agenlate.api.errors import install_error_handlers
from agenlate.db import DatabaseUnavailable, RepositoryError
from agenlate.repository._common import execute


class _Unreachable:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self):
        raise self._error


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("tls failed"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("cut")],
)
async def test_a_dropped_connection_is_reported_as_unavailable(error) -> None:
    with pytest.raises(DatabaseUnavailable):
        await execute(_Unreachable(error), context="list_rooms")


async def test_the_original_error_is_not_chained() -> None:
    """The httpx error holds the request, and the request holds the user's
    token; chaining it would carry both into the log."""
    with pytest.raises(DatabaseUnavailable) as caught:
        await execute(_Unreachable(httpx.ConnectError("x")), context="list_rooms")

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


async def test_it_is_still_a_repository_error() -> None:
    """Anything already handling repository failures keeps working."""
    assert issubclass(DatabaseUnavailable, RepositoryError)


async def test_the_api_answers_503_with_something_to_act_on() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise DatabaseUnavailable("list_rooms: ConnectError")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/boom")

    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "unavailable"
    assert "try again" in body["message"].lower()
    assert "ConnectError" not in response.text
