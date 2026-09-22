"""Round-trip tests for every repository function against a real project.

Run with: pytest -m integration
"""

from __future__ import annotations

import pytest
from supabase import AsyncClient

from agenlate.models import (
    AgentCreate,
    AgentUpdate,
    Emitter,
    MessageCreate,
    RoomCreate,
    RoomUpdate,
    UsageEventCreate,
)
from agenlate.repository import agents, messages, rooms, usage, users

pytestmark = pytest.mark.integration


async def seed_user(db: AsyncClient, user) -> None:
    await users.ensure_user(db, user.id, user.email)


async def make_agent(db: AsyncClient, user, name: str = "Researcher"):
    return await agents.create_agent(
        db,
        user.id,
        AgentCreate(name=name, role="finds information", system_prompt="you research"),
    )


async def make_room(db: AsyncClient, user, name: str = "Blog post"):
    return await rooms.create_room(
        db, user.id, RoomCreate(name=name, objective="write about coffee")
    )


class TestUsers:
    async def test_ensure_user_creates_then_returns_the_row(self, alice_db, alice) -> None:
        created = await users.ensure_user(alice_db, alice.id, alice.email)

        assert created.id == alice.id
        assert created.email == alice.email
        assert created.credit_balance == 0

    async def test_ensure_user_is_idempotent(self, alice_db, alice) -> None:
        """First login can fire twice concurrently; the second must not error."""
        first = await users.ensure_user(alice_db, alice.id, alice.email)
        second = await users.ensure_user(alice_db, alice.id, alice.email)

        assert first.id == second.id

    async def test_get_user_returns_none_when_absent(self, alice_db) -> None:
        assert await users.get_user(alice_db, "00000000-0000-0000-0000-000000000000") is None


class TestAgents:
    async def test_create_and_read_back(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        created = await make_agent(alice_db, alice)

        fetched = await agents.get_agent(alice_db, created.id)

        assert fetched is not None
        assert fetched.name == "Researcher"
        assert fetched.creator_id == alice.id

    async def test_list_returns_only_this_users_agents(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        await make_agent(alice_db, alice, "One")
        await make_agent(alice_db, alice, "Two")

        listed = await agents.list_agents_for_user(alice_db, alice.id)

        assert {a.name for a in listed} == {"One", "Two"}

    async def test_update_changes_only_supplied_fields(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        created = await make_agent(alice_db, alice)

        updated = await agents.update_agent(alice_db, created.id, AgentUpdate(name="Renamed"))

        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.system_prompt == created.system_prompt

    async def test_update_bumps_updated_at(self, alice_db, alice) -> None:
        """Verifies the database trigger fires, not just that the row changed."""
        await seed_user(alice_db, alice)
        created = await make_agent(alice_db, alice)

        updated = await agents.update_agent(alice_db, created.id, AgentUpdate(name="Renamed"))

        assert updated is not None
        assert updated.updated_at > created.updated_at

    async def test_delete_reports_whether_a_row_went(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        created = await make_agent(alice_db, alice)

        assert await agents.delete_agent(alice_db, created.id) is True
        assert await agents.delete_agent(alice_db, created.id) is False
        assert await agents.get_agent(alice_db, created.id) is None


class TestRooms:
    async def test_create_and_read_back(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        created = await make_room(alice_db, alice)

        fetched = await rooms.get_room(alice_db, created.id)

        assert fetched is not None
        assert fetched.objective == "write about coffee"

    async def test_list_is_newest_first(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        await make_room(alice_db, alice, "Older")
        newer = await make_room(alice_db, alice, "Newer")

        listed = await rooms.list_rooms_with_agents_for_user(alice_db, alice.id)

        assert listed[0].room.id == newer.id

    async def test_update_and_delete(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        created = await make_room(alice_db, alice)

        updated = await rooms.update_room(alice_db, created.id, RoomUpdate(name="Renamed"))
        assert updated is not None and updated.name == "Renamed"

        assert await rooms.delete_room(alice_db, created.id) is True
        assert await rooms.get_room(alice_db, created.id) is None


class TestRoster:
    async def test_room_with_agents_fetches_both_in_one_call(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)
        first = await make_agent(alice_db, alice, "Researcher")
        second = await make_agent(alice_db, alice, "Writer")
        await rooms.add_agent_to_room(alice_db, room.id, first.id)
        await rooms.add_agent_to_room(alice_db, room.id, second.id)

        loaded = await rooms.get_room_with_agents(alice_db, room.id)

        assert loaded is not None
        assert loaded.room.id == room.id
        assert {a.name for a in loaded.agents} == {"Researcher", "Writer"}

    async def test_roster_renders_one_line_per_agent(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)
        agent = await make_agent(alice_db, alice)
        await rooms.add_agent_to_room(alice_db, room.id, agent.id)

        loaded = await rooms.get_room_with_agents(alice_db, room.id)

        assert loaded is not None
        assert loaded.roster().count("\n") == 0
        assert agent.id in loaded.roster()

    async def test_adding_the_same_agent_twice_is_harmless(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)
        agent = await make_agent(alice_db, alice)

        await rooms.add_agent_to_room(alice_db, room.id, agent.id)
        await rooms.add_agent_to_room(alice_db, room.id, agent.id)

        loaded = await rooms.get_room_with_agents(alice_db, room.id)
        assert loaded is not None and len(loaded.agents) == 1

    async def test_remove_agent(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)
        agent = await make_agent(alice_db, alice)
        await rooms.add_agent_to_room(alice_db, room.id, agent.id)

        assert await rooms.remove_agent_from_room(alice_db, room.id, agent.id) is True

        loaded = await rooms.get_room_with_agents(alice_db, room.id)
        assert loaded is not None and loaded.agents == []

    async def test_empty_room_loads_with_no_agents(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)

        loaded = await rooms.get_room_with_agents(alice_db, room.id)

        assert loaded is not None and loaded.agents == []


class TestMessages:
    async def test_append_and_list_in_order(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)

        for i in range(5):
            await messages.append_message(
                alice_db,
                MessageCreate(
                    room_id=room.id,
                    emitter=Emitter.SUPERVISOR,
                    emitter_name="Supervisor",
                    content=f"turn {i}",
                ),
            )

        listed = await messages.list_messages(alice_db, room.id)

        assert [m.content for m in listed] == [f"turn {i}" for i in range(5)]
        assert [m.seq for m in listed] == sorted(m.seq for m in listed)

    async def test_seq_orders_messages_written_in_the_same_instant(
        self, alice_db, alice
    ) -> None:
        """The reason seq exists: a supervisor decision and the agent message it
        triggers can share a timestamp, and the transcript must still replay in
        the order things actually happened."""
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)

        decision = await messages.append_message(
            alice_db,
            MessageCreate(
                room_id=room.id,
                emitter=Emitter.SUPERVISOR,
                emitter_name="Supervisor",
                content="dispatching",
            ),
        )
        reply = await messages.append_message(
            alice_db,
            MessageCreate(
                room_id=room.id,
                emitter=Emitter.AGENT,
                emitter_name="Researcher",
                content="done",
            ),
        )

        assert reply.seq > decision.seq

    async def test_after_seq_streams_only_new_messages(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)
        first = await messages.append_message(
            alice_db,
            MessageCreate(
                room_id=room.id, emitter=Emitter.USER, emitter_name="Alice", content="one"
            ),
        )
        await messages.append_message(
            alice_db,
            MessageCreate(
                room_id=room.id, emitter=Emitter.USER, emitter_name="Alice", content="two"
            ),
        )

        newer = await messages.list_messages(alice_db, room.id, after_seq=first.seq)

        assert [m.content for m in newer] == ["two"]

    async def test_every_emitter_round_trips(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)

        for emitter in Emitter:
            written = await messages.append_message(
                alice_db,
                MessageCreate(
                    room_id=room.id,
                    emitter=emitter,
                    emitter_name="x",
                    content=emitter.value,
                ),
            )
            assert written.emitter is emitter


class TestUsage:
    async def test_priced_request_records_its_cost(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)

        event = await usage.record_usage_event(
            alice_db,
            UsageEventCreate(
                user_id=alice.id,
                room_id=room.id,
                model="anthropic/claude-sonnet-4.5",
                prompt_tokens=1200,
                completion_tokens=300,
                cost_usd=0.004521,
                provider_generation_id="gen-123",
            ),
        )

        assert event.is_priced is True
        assert event.cost_usd == pytest.approx(0.004521)
        assert event.total_tokens == 1500

    async def test_unpriced_request_records_null_never_zero(self, alice_db, alice) -> None:
        """A provider that reports no cost must not be recorded as free —
        that would silently understate what the user spent."""
        await seed_user(alice_db, alice)

        event = await usage.record_usage_event(
            alice_db,
            UsageEventCreate(user_id=alice.id, model="unknown/model", cost_usd=None),
        )

        assert event.is_priced is False
        assert event.cost_usd is None

    async def test_zero_cost_is_recorded_as_priced(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)

        event = await usage.record_usage_event(
            alice_db,
            UsageEventCreate(user_id=alice.id, model="free/model", cost_usd=0.0),
        )

        assert event.is_priced is True
        assert event.cost_usd == 0

    async def test_usage_survives_deletion_of_its_room(self, alice_db, alice) -> None:
        """Deleting a room must not erase the record of money already spent."""
        await seed_user(alice_db, alice)
        room = await make_room(alice_db, alice)
        await usage.record_usage_event(
            alice_db,
            UsageEventCreate(user_id=alice.id, room_id=room.id, model="m", cost_usd=0.01),
        )

        await rooms.delete_room(alice_db, room.id)

        remaining = await usage.list_usage_for_user(alice_db, alice.id)
        assert len(remaining) == 1
        assert remaining[0].room_id is None

    async def test_list_for_user_is_newest_first(self, alice_db, alice) -> None:
        await seed_user(alice_db, alice)
        for cost in (0.01, 0.02, 0.03):
            await usage.record_usage_event(
                alice_db, UsageEventCreate(user_id=alice.id, model="m", cost_usd=cost)
            )

        listed = await usage.list_usage_for_user(alice_db, alice.id)

        assert len(listed) == 3
        assert listed[0].created_at >= listed[-1].created_at


class TestIsolationThroughTheRepository:
    """Row-level security was verified in SQL when the policies were written.
    These confirm the repository layer inherits it rather than routing around
    it — an accidental service-role client here would silently undo all of it.
    """

    async def test_one_user_cannot_read_anothers_rooms(
        self, alice_db, alice, bob_db, bob
    ) -> None:
        await seed_user(alice_db, alice)
        await seed_user(bob_db, bob)
        alice_room = await make_room(alice_db, alice, "Alice private")

        assert await rooms.get_room(bob_db, alice_room.id) is None
        assert await rooms.list_rooms_with_agents_for_user(bob_db, alice.id) == []

    async def test_one_user_cannot_read_anothers_agents(
        self, alice_db, alice, bob_db, bob
    ) -> None:
        await seed_user(alice_db, alice)
        await seed_user(bob_db, bob)
        alice_agent = await make_agent(alice_db, alice)

        assert await agents.get_agent(bob_db, alice_agent.id) is None

    async def test_one_user_cannot_read_anothers_transcript(
        self, alice_db, alice, bob_db, bob
    ) -> None:
        await seed_user(alice_db, alice)
        await seed_user(bob_db, bob)
        alice_room = await make_room(alice_db, alice)
        await messages.append_message(
            alice_db,
            MessageCreate(
                room_id=alice_room.id,
                emitter=Emitter.AGENT,
                emitter_name="Researcher",
                content="confidential",
            ),
        )

        assert await messages.list_messages(bob_db, alice_room.id) == []

    async def test_one_user_cannot_read_anothers_usage(
        self, alice_db, alice, bob_db, bob
    ) -> None:
        await seed_user(alice_db, alice)
        await seed_user(bob_db, bob)
        await usage.record_usage_event(
            alice_db, UsageEventCreate(user_id=alice.id, model="m", cost_usd=1.23)
        )

        assert await usage.list_usage_for_user(bob_db, alice.id) == []

    async def test_deleting_another_users_room_does_nothing(
        self, alice_db, alice, bob_db, bob
    ) -> None:
        await seed_user(alice_db, alice)
        await seed_user(bob_db, bob)
        alice_room = await make_room(alice_db, alice)

        assert await rooms.delete_room(bob_db, alice_room.id) is False
        assert await rooms.get_room(alice_db, alice_room.id) is not None
