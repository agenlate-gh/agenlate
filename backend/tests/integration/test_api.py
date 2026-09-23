"""The HTTP API, end to end against a real project.

These run through the whole stack — token verification, a user-scoped database
client, row-level security — because that is where the isolation guarantees
actually live. Mocking any of it would test the handlers and not the thing that
protects one user's data from another.

Run with: pytest -m integration
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agenlate.agents.tools import WEB_SEARCH
from agenlate.config import Settings
from agenlate.main import create_app
from agenlate.repository import users

pytestmark = pytest.mark.integration

AGENT = {
    "name": "Researcher",
    "role": "finds and verifies information",
    "system_prompt": "You research carefully.",
}
ROOM = {"name": "Blog post", "objective": "Write about coffee trends"}


@pytest_asyncio.fixture
async def api(settings: Settings):
    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def auth(user) -> dict:
    return {"Authorization": f"Bearer {user.access_token}"}


@pytest_asyncio.fixture
async def alice_ready(alice_db, alice):
    await users.ensure_user(alice_db, alice.id, alice.email)
    return alice


@pytest_asyncio.fixture
async def bob_ready(bob_db, bob):
    await users.ensure_user(bob_db, bob.id, bob.email)
    return bob


class TestAuthenticationRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/agents"),
            ("post", "/api/agents"),
            ("get", "/api/agents/some-id"),
            ("get", "/api/rooms"),
            ("post", "/api/rooms"),
            ("get", "/api/rooms/some-id"),
            ("get", "/api/rooms/some-id/messages"),
            ("get", "/api/usage/summary"),
            ("get", "/api/usage/rooms"),
        ],
    )
    async def test_every_endpoint_refuses_an_anonymous_caller(
        self, api, method, path
    ) -> None:
        response = await api.request(method.upper(), path, json={})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"

    async def test_a_forged_token_is_refused(self, api) -> None:
        response = await api.get(
            "/api/agents", headers={"Authorization": "Bearer not-a-real-token"}
        )

        assert response.status_code == 401


class TestAgents:
    async def test_create_and_read_back(self, api, alice_ready) -> None:
        created = await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))

        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "Researcher"
        assert body["enabled_tools"] is None  # null means the defaults

        fetched = await api.get(f"/api/agents/{body['id']}", headers=auth(alice_ready))
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]

    async def test_list_returns_only_the_callers_agents(
        self, api, alice_ready, bob_ready
    ) -> None:
        await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))

        listed = await api.get("/api/agents", headers=auth(bob_ready))

        assert listed.status_code == 200
        assert listed.json() == []

    async def test_update_changes_only_what_was_sent(self, api, alice_ready) -> None:
        created = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()

        updated = await api.patch(
            f"/api/agents/{created['id']}",
            json={"name": "Renamed"},
            headers=auth(alice_ready),
        )

        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed"
        assert updated.json()["system_prompt"] == AGENT["system_prompt"]

    async def test_delete_then_get_is_not_found(self, api, alice_ready) -> None:
        created = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()

        assert (
            await api.delete(f"/api/agents/{created['id']}", headers=auth(alice_ready))
        ).status_code == 204
        assert (
            await api.get(f"/api/agents/{created['id']}", headers=auth(alice_ready))
        ).status_code == 404

    async def test_tools_can_be_set_and_cleared(self, api, alice_ready) -> None:
        created = (
            await api.post(
                "/api/agents",
                json={**AGENT, "enabled_tools": [WEB_SEARCH]},
                headers=auth(alice_ready),
            )
        ).json()
        assert created["enabled_tools"] == [WEB_SEARCH]

        cleared = await api.patch(
            f"/api/agents/{created['id']}",
            json={"enabled_tools": []},
            headers=auth(alice_ready),
        )

        assert cleared.json()["enabled_tools"] == []

    async def test_an_unusable_tool_is_refused_at_the_boundary(
        self, api, alice_ready
    ) -> None:
        """Accepting it and dropping it later would leave the user looking at
        an agent claiming a capability it does not have."""
        response = await api.post(
            "/api/agents",
            json={**AGENT, "enabled_tools": ["openrouter:shell"]},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422

    async def test_an_over_long_prompt_is_refused(self, api, alice_ready) -> None:
        response = await api.post(
            "/api/agents",
            json={**AGENT, "system_prompt": "x" * 9000},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"


class TestRooms:
    async def test_create_with_a_roster(self, api, alice_ready) -> None:
        agent = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()

        created = await api.post(
            "/api/rooms",
            json={**ROOM, "agent_ids": [agent["id"]]},
            headers=auth(alice_ready),
        )

        assert created.status_code == 201
        assert [a["id"] for a in created.json()["agents"]] == [agent["id"]]

    async def test_get_returns_the_room_and_its_roster_together(
        self, api, alice_ready
    ) -> None:
        """One request, because the room view always needs both."""
        agent = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()
        room = (
            await api.post(
                "/api/rooms",
                json={**ROOM, "agent_ids": [agent["id"]]},
                headers=auth(alice_ready),
            )
        ).json()

        fetched = await api.get(f"/api/rooms/{room['id']}", headers=auth(alice_ready))

        assert fetched.json()["objective"] == ROOM["objective"]
        assert len(fetched.json()["agents"]) == 1

    async def test_seating_an_agent_twice_is_harmless(self, api, alice_ready) -> None:
        """A client retrying a dropped request should not be punished."""
        agent = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()
        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        path = f"/api/rooms/{room['id']}/agents/{agent['id']}"

        assert (await api.put(path, headers=auth(alice_ready))).status_code == 204
        assert (await api.put(path, headers=auth(alice_ready))).status_code == 204

        fetched = await api.get(f"/api/rooms/{room['id']}", headers=auth(alice_ready))
        assert len(fetched.json()["agents"]) == 1

    async def test_remove_an_agent(self, api, alice_ready) -> None:
        agent = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()
        room = (
            await api.post(
                "/api/rooms",
                json={**ROOM, "agent_ids": [agent["id"]]},
                headers=auth(alice_ready),
            )
        ).json()

        removed = await api.delete(
            f"/api/rooms/{room['id']}/agents/{agent['id']}", headers=auth(alice_ready)
        )

        assert removed.status_code == 204
        fetched = await api.get(f"/api/rooms/{room['id']}", headers=auth(alice_ready))
        assert fetched.json()["agents"] == []

    async def test_update_and_delete(self, api, alice_ready) -> None:
        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()

        updated = await api.patch(
            f"/api/rooms/{room['id']}", json={"name": "Renamed"}, headers=auth(alice_ready)
        )
        assert updated.json()["name"] == "Renamed"

        assert (
            await api.delete(f"/api/rooms/{room['id']}", headers=auth(alice_ready))
        ).status_code == 204

    async def test_a_new_room_is_active(self, api, alice_ready) -> None:
        """A user who has just created a room means to use it."""
        created = await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))

        assert created.json()["status"] == "active"

    async def test_a_room_can_be_paused_and_resumed(self, api, alice_ready) -> None:
        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()

        paused = await api.patch(
            f"/api/rooms/{room['id']}",
            json={"status": "paused"},
            headers=auth(alice_ready),
        )
        assert paused.json()["status"] == "paused"

        resumed = await api.patch(
            f"/api/rooms/{room['id']}",
            json={"status": "active"},
            headers=auth(alice_ready),
        )
        assert resumed.json()["status"] == "active"

    async def test_pausing_leaves_everything_else_alone(
        self, api, alice_ready
    ) -> None:
        """The point of pausing rather than deleting is that the room survives
        it."""
        agent = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()
        room = (
            await api.post(
                "/api/rooms",
                json={**ROOM, "agent_ids": [agent["id"]]},
                headers=auth(alice_ready),
            )
        ).json()

        await api.patch(
            f"/api/rooms/{room['id']}",
            json={"status": "paused"},
            headers=auth(alice_ready),
        )

        fetched = (
            await api.get(f"/api/rooms/{room['id']}", headers=auth(alice_ready))
        ).json()
        assert fetched["name"] == room["name"]
        assert fetched["objective"] == room["objective"]
        assert [a["id"] for a in fetched["agents"]] == [agent["id"]]

    async def test_an_unknown_status_is_refused(self, api, alice_ready) -> None:
        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()

        response = await api.patch(
            f"/api/rooms/{room['id']}",
            json={"status": "archived"},
            headers=auth(alice_ready),
        )

        assert response.status_code == 422


class TestOneUserCannotReachAnother:
    """The acceptance criterion. Every one of these answers 404 rather than
    403: telling Bob that Alice's room exists but is not his confirms it
    exists, which is itself a leak.
    """

    @pytest_asyncio.fixture
    async def alices_room(self, api, alice_ready):
        agent = (
            await api.post("/api/agents", json=AGENT, headers=auth(alice_ready))
        ).json()
        room = (
            await api.post(
                "/api/rooms",
                json={**ROOM, "agent_ids": [agent["id"]]},
                headers=auth(alice_ready),
            )
        ).json()
        return agent, room

    async def test_reading_a_room(self, api, alices_room, bob_ready) -> None:
        _, room = alices_room

        response = await api.get(f"/api/rooms/{room['id']}", headers=auth(bob_ready))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    async def test_reading_an_agent(self, api, alices_room, bob_ready) -> None:
        agent, _ = alices_room

        assert (
            await api.get(f"/api/agents/{agent['id']}", headers=auth(bob_ready))
        ).status_code == 404

    async def test_reading_a_transcript(self, api, alices_room, bob_ready) -> None:
        _, room = alices_room

        assert (
            await api.get(f"/api/rooms/{room['id']}/messages", headers=auth(bob_ready))
        ).status_code == 404

    async def test_updating_a_room(self, api, alices_room, bob_ready) -> None:
        _, room = alices_room

        response = await api.patch(
            f"/api/rooms/{room['id']}", json={"name": "hijacked"}, headers=auth(bob_ready)
        )

        assert response.status_code == 404

    async def test_deleting_a_room(self, api, alices_room, bob_ready, alice_ready) -> None:
        _, room = alices_room

        assert (
            await api.delete(f"/api/rooms/{room['id']}", headers=auth(bob_ready))
        ).status_code == 404
        assert (
            await api.get(f"/api/rooms/{room['id']}", headers=auth(alice_ready))
        ).status_code == 200

    async def test_deleting_an_agent(self, api, alices_room, bob_ready) -> None:
        agent, _ = alices_room

        assert (
            await api.delete(f"/api/agents/{agent['id']}", headers=auth(bob_ready))
        ).status_code == 404

    async def test_seating_an_agent_in_someone_elses_room(
        self, api, alices_room, bob_ready
    ) -> None:
        agent, room = alices_room

        response = await api.put(
            f"/api/rooms/{room['id']}/agents/{agent['id']}", headers=auth(bob_ready)
        )

        assert response.status_code == 404


class TestTranscriptPaging:
    @pytest_asyncio.fixture
    async def room_with_messages(self, api, alice_db, alice_ready):
        from agenlate.models import Emitter, MessageCreate
        from agenlate.repository import messages as repo

        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        for i in range(7):
            await repo.append_message(
                alice_db,
                MessageCreate(
                    room_id=room["id"],
                    emitter=Emitter.AGENT,
                    emitter_name="Researcher",
                    content=f"message {i}",
                ),
            )
        return room

    async def test_returns_the_transcript_in_order(
        self, api, room_with_messages, alice_ready
    ) -> None:
        page = (
            await api.get(
                f"/api/rooms/{room_with_messages['id']}/messages", headers=auth(alice_ready)
            )
        ).json()

        assert [m["content"] for m in page["items"]] == [f"message {i}" for i in range(7)]
        assert page["next_after_seq"] is None

    async def test_a_full_page_offers_a_cursor(
        self, api, room_with_messages, alice_ready
    ) -> None:
        page = (
            await api.get(
                f"/api/rooms/{room_with_messages['id']}/messages?limit=3",
                headers=auth(alice_ready),
            )
        ).json()

        assert len(page["items"]) == 3
        assert page["next_after_seq"] == page["items"][-1]["seq"]

    async def test_the_cursor_continues_without_gaps_or_repeats(
        self, api, room_with_messages, alice_ready
    ) -> None:
        """Paging by seq rather than offset, because a transcript grows while
        it is being read."""
        collected: list[str] = []
        cursor: int | None = None

        for _ in range(5):
            url = f"/api/rooms/{room_with_messages['id']}/messages?limit=3"
            if cursor is not None:
                url += f"&after_seq={cursor}"
            page = (await api.get(url, headers=auth(alice_ready))).json()
            collected += [m["content"] for m in page["items"]]
            cursor = page["next_after_seq"]
            if cursor is None:
                break

        assert collected == [f"message {i}" for i in range(7)]

    async def test_an_oversized_limit_is_refused(
        self, api, room_with_messages, alice_ready
    ) -> None:
        response = await api.get(
            f"/api/rooms/{room_with_messages['id']}/messages?limit=5000",
            headers=auth(alice_ready),
        )

        assert response.status_code == 422


class TestUsageSummary:
    """Phase 1 metrics. Deliberately does not lead with token volume: the same
    room measured $0.000179 without web search and $0.007285 with it, so tokens
    answer a question nobody has.
    """

    async def test_a_new_account_reports_nothing(self, api, alice_ready) -> None:
        summary = (await api.get("/api/usage/summary", headers=auth(alice_ready))).json()

        assert summary["requests"] == 0
        assert summary["cost_usd"] == 0
        assert summary["cost_is_complete"] is True

    async def test_it_sums_this_users_own_usage(self, api, alice_db, alice_ready) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        for cost in (0.01, 0.02):
            await usage_repo.record_usage_event(
                alice_db,
                UsageEventCreate(
                    user_id=alice_ready.id, model="m",
                    prompt_tokens=100, completion_tokens=20, cost_usd=cost,
                ),
            )

        summary = (await api.get("/api/usage/summary", headers=auth(alice_ready))).json()

        assert summary["requests"] == 2
        assert summary["cost_usd"] == pytest.approx(0.03)
        assert summary["prompt_tokens"] == 200

    async def test_unpriced_requests_mark_the_total_as_a_floor(
        self, api, alice_db, alice_ready
    ) -> None:
        """Reporting a total as if it were complete would understate what the
        user spent."""
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        await usage_repo.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=0.01)
        )
        await usage_repo.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=None)
        )

        summary = (await api.get("/api/usage/summary", headers=auth(alice_ready))).json()

        assert summary["unpriced_requests"] == 1
        assert summary["cost_is_complete"] is False
        assert summary["cost_usd"] == pytest.approx(0.01)

    async def test_tool_spending_is_reported_separately(
        self, api, alice_db, alice_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=0.0002),
        )
        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice_ready.id, model="m", cost_usd=0.0073, server_tool_calls=2
            ),
        )

        summary = (await api.get("/api/usage/summary", headers=auth(alice_ready))).json()

        assert summary["tool_enabled_requests"] == 1
        assert summary["tool_enabled_cost_usd"] == pytest.approx(0.0073)

    async def test_one_user_cannot_see_anothers_spending(
        self, api, alice_db, alice_ready, bob_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        await usage_repo.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=5.0)
        )

        summary = (await api.get("/api/usage/summary", headers=auth(bob_ready))).json()

        assert summary["requests"] == 0
        assert summary["cost_usd"] == 0

    async def test_it_requires_a_signed_in_caller(self, api) -> None:
        assert (await api.get("/api/usage/summary")).status_code == 401


class TestUsageByRoom:
    """What the lobby shows on each card. One request for every room rather
    than one per room."""

    async def test_a_new_account_has_nothing_to_report(
        self, api, alice_ready
    ) -> None:
        assert (await api.get("/api/usage/rooms", headers=auth(alice_ready))).json() == []

    async def test_spending_is_attributed_to_the_room_that_caused_it(
        self, api, alice_db, alice_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        cheap = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        dear = (
            await api.post(
                "/api/rooms", json={**ROOM, "name": "Expensive"}, headers=auth(alice_ready)
            )
        ).json()

        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice_ready.id, room_id=cheap["id"], model="m", cost_usd=0.01
            ),
        )
        for _ in range(2):
            await usage_repo.record_usage_event(
                alice_db,
                UsageEventCreate(
                    user_id=alice_ready.id, room_id=dear["id"], model="m", cost_usd=0.25
                ),
            )

        by_room = (
            await api.get("/api/usage/rooms", headers=auth(alice_ready))
        ).json()

        # Most expensive first, so the lobby does not have to sort.
        assert [r["room_id"] for r in by_room] == [dear["id"], cheap["id"]]
        assert by_room[0]["cost_usd"] == pytest.approx(0.50)
        assert by_room[0]["requests"] == 2
        assert by_room[1]["cost_usd"] == pytest.approx(0.01)

    async def test_a_room_that_has_never_run_is_absent(
        self, api, alice_ready
    ) -> None:
        """Absent rather than zero. Recording a zero for a room nobody has run
        would be inventing a fact; the caller reads a missing room as nothing
        spent."""
        await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))

        assert (await api.get("/api/usage/rooms", headers=auth(alice_ready))).json() == []

    async def test_an_unpriced_request_marks_that_room_incomplete(
        self, api, alice_db, alice_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice_ready.id, room_id=room["id"], model="m", cost_usd=0.01
            ),
        )
        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice_ready.id, room_id=room["id"], model="m", cost_usd=None
            ),
        )

        entry = (await api.get("/api/usage/rooms", headers=auth(alice_ready))).json()[0]

        assert entry["unpriced_requests"] == 1
        assert entry["cost_is_complete"] is False
        assert entry["cost_usd"] == pytest.approx(0.01)

    async def test_one_user_cannot_see_anothers_rooms(
        self, api, alice_db, alice_ready, bob_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice_ready.id, room_id=room["id"], model="m", cost_usd=5.0
            ),
        )

        assert (await api.get("/api/usage/rooms", headers=auth(bob_ready))).json() == []

    async def test_it_requires_a_signed_in_caller(self, api) -> None:
        assert (await api.get("/api/usage/rooms")).status_code == 401


class TestUsageDaily:
    """The billing chart's series."""

    async def test_quiet_days_are_present_as_zero(self, api, alice_ready) -> None:
        """A chart that plots only the days with activity draws a straight line
        through a fortnight of nothing, which reads as steady spending."""
        days = (await api.get("/api/usage/daily?days=7", headers=auth(alice_ready))).json()

        assert len(days) == 8  # seven days back, plus today
        assert all(day["cost_usd"] == 0 for day in days)
        assert [day["day"] for day in days] == sorted(day["day"] for day in days)

    async def test_todays_spending_lands_on_today(
        self, api, alice_db, alice_ready
    ) -> None:
        from datetime import datetime, timezone

        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        await usage_repo.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=0.02)
        )

        days = (await api.get("/api/usage/daily?days=7", headers=auth(alice_ready))).json()
        today = datetime.now(timezone.utc).date().isoformat()

        entry = next(day for day in days if day["day"] == today)
        assert entry["cost_usd"] == pytest.approx(0.02)
        assert entry["requests"] == 1

    async def test_it_requires_a_signed_in_caller(self, api) -> None:
        assert (await api.get("/api/usage/daily")).status_code == 401


class TestUsageEvents:
    """The audit log."""

    async def test_events_come_back_newest_first_with_their_room(
        self, api, alice_db, alice_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        for cost in (0.01, 0.02):
            await usage_repo.record_usage_event(
                alice_db,
                UsageEventCreate(
                    user_id=alice_ready.id,
                    room_id=room["id"],
                    model="qwen/qwen3.7-flash",
                    cost_usd=cost,
                ),
            )

        events = (await api.get("/api/usage/events", headers=auth(alice_ready))).json()

        assert len(events) == 2
        assert events[0]["created_at"] >= events[1]["created_at"]
        assert events[0]["room_name"] == room["name"]
        assert events[0]["model"] == "qwen/qwen3.7-flash"

    async def test_spending_outlives_the_room_it_came_from(
        self, api, alice_db, alice_ready
    ) -> None:
        """Deleting a room must not erase the record of money already spent."""
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        room = (await api.post("/api/rooms", json=ROOM, headers=auth(alice_ready))).json()
        await usage_repo.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice_ready.id, room_id=room["id"], model="m", cost_usd=0.01
            ),
        )
        await api.delete(f"/api/rooms/{room['id']}", headers=auth(alice_ready))

        events = (await api.get("/api/usage/events", headers=auth(alice_ready))).json()

        assert len(events) == 1
        assert events[0]["room_id"] is None
        assert events[0]["room_name"] is None
        assert events[0]["cost_usd"] == pytest.approx(0.01)

    async def test_an_unpriced_call_reports_no_cost_rather_than_zero(
        self, api, alice_db, alice_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        await usage_repo.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=None)
        )

        events = (await api.get("/api/usage/events", headers=auth(alice_ready))).json()

        assert events[0]["cost_usd"] is None

    async def test_one_user_cannot_see_anothers_events(
        self, api, alice_db, alice_ready, bob_ready
    ) -> None:
        from agenlate.models import UsageEventCreate
        from agenlate.repository import usage as usage_repo

        await usage_repo.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice_ready.id, model="m", cost_usd=9.0)
        )

        assert (await api.get("/api/usage/events", headers=auth(bob_ready))).json() == []

    async def test_it_requires_a_signed_in_caller(self, api) -> None:
        assert (await api.get("/api/usage/events")).status_code == 401
