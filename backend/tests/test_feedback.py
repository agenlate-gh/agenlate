"""In-product feedback: each answer stored under its question, as the user."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agenlate.api import feedback as feedback_api
from agenlate.api.deps import user_db
from agenlate.api.limits import WindowLimiter
from agenlate.auth import CurrentUser, current_user
from agenlate.main import create_app


class FakeTable:
    def __init__(self) -> None:
        self.inserted: list[dict] = []
        self.returning = None

    def table(self, name: str):
        assert name == "feedback"
        return self

    def insert(self, rows, returning=None):
        self.inserted.extend(rows)
        self.returning = returning
        return self

    async def execute(self):
        class Response:
            data = []

        return Response()


@pytest.fixture
def db(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(feedback_api, "_limiter", WindowLimiter(10, 3600))
    return fake


@pytest.fixture
async def api(settings, db):
    app = create_app(settings)
    app.dependency_overrides[current_user] = lambda: CurrentUser(id="u1", email="u1@example.com")
    app.dependency_overrides[user_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_each_answer_is_its_own_row_under_its_question(api, db) -> None:
    response = await api.post(
        "/api/feedback",
        json={"automate": "Weekly reports", "connect": "Gmail and Notion", "page": "/lobby"},
    )

    assert response.status_code == 201
    assert response.json() == {"saved": 2}
    assert [(r["question"], r["answer"]) for r in db.inserted] == [
        ("automate", "Weekly reports"),
        ("connect", "Gmail and Notion"),
    ]


async def test_answers_are_written_as_the_caller(api, db) -> None:
    """Row-level security checks this too; sending anything else would be refused."""
    await api.post("/api/feedback", json={"general": "Nice"})

    assert db.inserted[0]["user_id"] == "u1"


async def test_blank_answers_are_skipped(api, db) -> None:
    response = await api.post("/api/feedback", json={"automate": "   ", "general": "Love it"})

    assert response.json() == {"saved": 1}
    assert db.inserted[0]["question"] == "general"


async def test_an_empty_form_is_refused(api, db) -> None:
    response = await api.post("/api/feedback", json={"automate": "", "connect": "  "})

    assert response.status_code == 422
    assert db.inserted == []


async def test_rows_are_not_read_back(api, db) -> None:
    """Users may add answers but not read them, so asking for the inserted
    rows back would be refused by the database."""
    from postgrest.types import ReturnMethod

    await api.post("/api/feedback", json={"general": "Hi"})

    assert db.returning is ReturnMethod.minimal


async def test_a_stuck_button_cannot_flood_the_table(api, db, monkeypatch) -> None:
    monkeypatch.setattr(feedback_api, "_limiter", WindowLimiter(2, 3600))

    codes = [(await api.post("/api/feedback", json={"general": "x"})).status_code for _ in range(3)]

    assert codes == [201, 201, 429]


async def test_it_requires_a_signed_in_caller(settings) -> None:
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/feedback", json={"general": "x"})

    assert response.status_code == 401
