"""Usage aggregation against a real project.

Run with: pytest -m integration
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agenlate.billing import UsageContext, record, summarise
from agenlate.llm import Usage
from agenlate.models import RoomCreate
from agenlate.repository import rooms, users

pytestmark = pytest.mark.integration


async def seed(db, user):
    await users.ensure_user(db, user.id, user.email)
    return await rooms.create_room(
        db, user.id, RoomCreate(name="Room", objective="do something")
    )


class TestSummary:
    async def test_no_usage_summarises_to_zero(self, alice_db, alice) -> None:
        await seed(alice_db, alice)

        summary = await summarise(alice_db)

        assert summary.total_requests == 0
        assert summary.cost_usd == 0.0
        assert summary.coverage == 1.0

    async def test_aggregates_tokens_cost_and_tool_calls(self, alice_db, alice) -> None:
        room = await seed(alice_db, alice)
        context = UsageContext(user_id=alice.id, model="m", room_id=room.id)

        await record(
            alice_db,
            Usage.for_call(prompt_tokens=1000, completion_tokens=200, cost_usd=0.01,
                           server_tool_calls=2),
            context,
        )
        await record(
            alice_db,
            Usage.for_call(prompt_tokens=500, completion_tokens=100, cost_usd=0.02,
                           server_tool_calls=1),
            context,
        )

        summary = await summarise(alice_db)

        assert summary.total_requests == 2
        assert summary.total_tokens == 1800
        assert summary.cost_usd == pytest.approx(0.03)
        assert summary.server_tool_calls == 3
        assert summary.rooms_touched == 1

    async def test_unpriced_requests_are_counted_not_summed(self, alice_db, alice) -> None:
        """The cost total must stay a sum of what was actually reported, so a
        partial figure is never mistaken for a complete one."""
        room = await seed(alice_db, alice)
        context = UsageContext(user_id=alice.id, model="m", room_id=room.id)

        await record(alice_db, Usage.for_call(cost_usd=0.05), context)
        await record(alice_db, Usage.for_call(cost_usd=None), context)

        summary = await summarise(alice_db)

        assert summary.total_requests == 2
        assert summary.priced_requests == 1
        assert summary.unpriced_requests == 1
        assert summary.cost_usd == pytest.approx(0.05)
        assert summary.coverage == pytest.approx(0.5)
        assert summary.has_unpriced is True

    async def test_a_period_filter_narrows_the_window(self, alice_db, alice) -> None:
        room = await seed(alice_db, alice)
        context = UsageContext(user_id=alice.id, model="m", room_id=room.id)
        await record(alice_db, Usage.for_call(cost_usd=0.01), context)

        future = datetime.now(timezone.utc) + timedelta(days=1)
        summary = await summarise(alice_db, since=future)

        assert summary.total_requests == 0

    async def test_a_room_filter_narrows_to_one_room(self, alice_db, alice) -> None:
        first = await seed(alice_db, alice)
        second = await rooms.create_room(
            alice_db, alice.id, RoomCreate(name="Other", objective="other")
        )
        await record(
            alice_db,
            Usage.for_call(cost_usd=0.01),
            UsageContext(user_id=alice.id, model="m", room_id=first.id),
        )
        await record(
            alice_db,
            Usage.for_call(cost_usd=0.02),
            UsageContext(user_id=alice.id, model="m", room_id=second.id),
        )

        summary = await summarise(alice_db, room_id=second.id)

        assert summary.total_requests == 1
        assert summary.cost_usd == pytest.approx(0.02)

    async def test_the_summary_respects_row_level_security(
        self, alice_db, alice, bob_db, bob
    ) -> None:
        """The function is SECURITY INVOKER precisely so this holds. A DEFINER
        version would aggregate everyone's spending for whoever asked."""
        room = await seed(alice_db, alice)
        await users.ensure_user(bob_db, bob.id, bob.email)
        await record(
            alice_db,
            Usage.for_call(cost_usd=1.23),
            UsageContext(user_id=alice.id, model="m", room_id=room.id),
        )

        bobs_view = await summarise(bob_db)

        assert bobs_view.total_requests == 0
        assert bobs_view.cost_usd == 0.0
