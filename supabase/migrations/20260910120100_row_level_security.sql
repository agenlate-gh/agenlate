-- Row-level security.
--
-- Every table is enabled and forced. A user reaches only their own rows; child
-- tables are scoped through the room that owns them.
--
-- Two patterns are used deliberately:
--
--   (select auth.uid())   rather than a bare auth.uid(). The bare call is
--                         re-evaluated per row; wrapped in a subquery Postgres
--                         evaluates it once and caches it.
--
--   force row level       makes the policies apply to the table owner too.
--   security             postgres and service_role hold BYPASSRLS so the
--                         backend and dashboard are unaffected, but ownership
--                         alone stops being a way around the policies.

alter table public.users enable row level security;
alter table public.users force row level security;
alter table public.agents enable row level security;
alter table public.agents force row level security;
alter table public.rooms enable row level security;
alter table public.rooms force row level security;
alter table public.room_agents enable row level security;
alter table public.room_agents force row level security;
alter table public.messages enable row level security;
alter table public.messages force row level security;
alter table public.usage_events enable row level security;
alter table public.usage_events force row level security;

-- ---------------------------------------------------------------------------
-- Privileges
--
-- anon receives nothing: every table here is private to a signed-in user.
-- RLS filters rows, but grants decide who may reach the table at all, and both
-- are needed.
-- ---------------------------------------------------------------------------

revoke all on public.users, public.agents, public.rooms,
                public.room_agents, public.messages, public.usage_events
  from anon, authenticated;

grant select, insert, update on public.users to authenticated;
grant select, insert, update, delete on public.agents to authenticated;
grant select, insert, update, delete on public.rooms to authenticated;
grant select, insert, delete on public.room_agents to authenticated;
grant select, insert on public.messages to authenticated;
-- A ledger: append and read only. No update or delete grant, so a user cannot
-- rewrite their own record of what was spent.
grant select, insert on public.usage_events to authenticated;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------

drop policy if exists users_select_own on public.users;
create policy users_select_own on public.users
  for select to authenticated
  using ((select auth.uid()) = id);

drop policy if exists users_insert_own on public.users;
create policy users_insert_own on public.users
  for insert to authenticated
  with check ((select auth.uid()) = id);

drop policy if exists users_update_own on public.users;
create policy users_update_own on public.users
  for update to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- ---------------------------------------------------------------------------
-- agents
-- ---------------------------------------------------------------------------

drop policy if exists agents_select_own on public.agents;
create policy agents_select_own on public.agents
  for select to authenticated
  using ((select auth.uid()) = creator_id);

drop policy if exists agents_insert_own on public.agents;
create policy agents_insert_own on public.agents
  for insert to authenticated
  with check ((select auth.uid()) = creator_id);

drop policy if exists agents_update_own on public.agents;
create policy agents_update_own on public.agents
  for update to authenticated
  using ((select auth.uid()) = creator_id)
  with check ((select auth.uid()) = creator_id);

drop policy if exists agents_delete_own on public.agents;
create policy agents_delete_own on public.agents
  for delete to authenticated
  using ((select auth.uid()) = creator_id);

-- ---------------------------------------------------------------------------
-- rooms
-- ---------------------------------------------------------------------------

drop policy if exists rooms_select_own on public.rooms;
create policy rooms_select_own on public.rooms
  for select to authenticated
  using ((select auth.uid()) = creator_id);

drop policy if exists rooms_insert_own on public.rooms;
create policy rooms_insert_own on public.rooms
  for insert to authenticated
  with check ((select auth.uid()) = creator_id);

drop policy if exists rooms_update_own on public.rooms;
create policy rooms_update_own on public.rooms
  for update to authenticated
  using ((select auth.uid()) = creator_id)
  with check ((select auth.uid()) = creator_id);

drop policy if exists rooms_delete_own on public.rooms;
create policy rooms_delete_own on public.rooms
  for delete to authenticated
  using ((select auth.uid()) = creator_id);

-- ---------------------------------------------------------------------------
-- room_agents
--
-- Scoped through both parents. Checking only the room would let a user attach
-- another user's agent to their own room — they could not read it, but the
-- reference would exist and the Supervisor would be handed an id it must not
-- see.
-- ---------------------------------------------------------------------------

drop policy if exists room_agents_select_own on public.room_agents;
create policy room_agents_select_own on public.room_agents
  for select to authenticated
  using (
    exists (
      select 1 from public.rooms r
      where r.id = room_agents.room_id
        and r.creator_id = (select auth.uid())
    )
  );

drop policy if exists room_agents_insert_own on public.room_agents;
create policy room_agents_insert_own on public.room_agents
  for insert to authenticated
  with check (
    exists (
      select 1 from public.rooms r
      where r.id = room_agents.room_id
        and r.creator_id = (select auth.uid())
    )
    and exists (
      select 1 from public.agents a
      where a.id = room_agents.agent_id
        and a.creator_id = (select auth.uid())
    )
  );

drop policy if exists room_agents_delete_own on public.room_agents;
create policy room_agents_delete_own on public.room_agents
  for delete to authenticated
  using (
    exists (
      select 1 from public.rooms r
      where r.id = room_agents.room_id
        and r.creator_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- messages — scoped through the owning room
-- ---------------------------------------------------------------------------

drop policy if exists messages_select_own on public.messages;
create policy messages_select_own on public.messages
  for select to authenticated
  using (
    exists (
      select 1 from public.rooms r
      where r.id = messages.room_id
        and r.creator_id = (select auth.uid())
    )
  );

drop policy if exists messages_insert_own on public.messages;
create policy messages_insert_own on public.messages
  for insert to authenticated
  with check (
    exists (
      select 1 from public.rooms r
      where r.id = messages.room_id
        and r.creator_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- usage_events — append and read only
-- ---------------------------------------------------------------------------

drop policy if exists usage_events_select_own on public.usage_events;
create policy usage_events_select_own on public.usage_events
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists usage_events_insert_own on public.usage_events;
create policy usage_events_insert_own on public.usage_events
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
