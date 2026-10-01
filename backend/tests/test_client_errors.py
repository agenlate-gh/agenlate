"""Crash reports from the browser."""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.api import client_errors
from agenlate.main import create_app

KEY = "sk-or-v1-" + "0123456789abcdef" * 3


@pytest.fixture
async def api(settings):
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def reports(monkeypatch):
    """What the endpoint logged, captured at the logger itself."""
    seen: list[logging.LogRecord] = []
    monkeypatch.setattr(
        client_errors.log, "warning", lambda msg, extra=None: seen.append(extra or {})
    )
    return seen


async def test_a_crash_is_written_to_the_log(api, reports) -> None:
    response = await api.post(
        "/api/client-errors",
        json={
            "message": "NotFoundError: Failed to execute 'insertBefore' on 'Node'",
            "stack": "at insertBefore (chunk.js:1:2)",
            "path": "/rooms/abc",
        },
    )

    assert response.status_code == 204
    assert "insertBefore" in reports[0]["client_message"]
    assert reports[0]["client_path"] == "/rooms/abc"


async def test_no_login_is_needed(api, reports) -> None:
    """A crash can happen on the login page, or because the session broke."""
    response = await api.post("/api/client-errors", json={"message": "boom"})

    assert response.status_code == 204


async def test_a_key_in_a_report_never_reaches_the_log(api, reports) -> None:
    await api.post(
        "/api/client-errors",
        json={"message": f"bad value {KEY}", "stack": f"key={KEY}", "path": f"/x?k={KEY}"},
    )

    assert KEY not in str(reports[0])


async def test_an_oversized_report_is_refused(api, reports) -> None:
    response = await api.post("/api/client-errors", json={"message": "x" * 5000})

    assert response.status_code == 422
    assert reports == []


async def test_a_crash_loop_cannot_flood_the_log(api, reports) -> None:
    """Over the limit the report is dropped, but still answered 204: a page
    stuck crashing should not also get an error about reporting its error."""
    codes = [
        (await api.post("/api/client-errors", json={"message": f"boom {i}"})).status_code
        for i in range(client_errors.REPORTS_PER_ADDRESS + 5)
    ]

    assert set(codes) == {204}
    assert len(reports) == client_errors.REPORTS_PER_ADDRESS
