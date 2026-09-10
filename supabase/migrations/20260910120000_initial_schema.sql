-- Initial schema: users, agents, rooms, room_agents, messages, usage_events.
--
-- Conventions used throughout:
--   * lowercase identifiers, unquoted
--   * text over varchar(n); length limits expressed as check constraints
--   * timestamptz, never timestamp
--   * numeric for money, never float
--   * every foreign key column carries an index (Postgres does not add one)

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- users
--
-- Mirrors auth.users. The application row exists so we can attach a credit
-- balance and application-level metadata without touching the auth schema.
-- ---------------------------------------------------------------------------

create table if not exists public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  -- Phase 2 balance. Present from the start so the column does not have to be
  -- added later against a populated table; unused while the Beta is BYOK.
  credit_balance numeric(12, 4) not null default 0 check (credit_balance >= 0),
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- agents — a user-designed worker profile
-- ---------------------------------------------------------------------------

create table if not exists public.agents (
  id uuid primary key default gen_random_uuid(),
  creator_id uuid not null references public.users (id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 100),
  role text not null check (length(btrim(role)) between 1 and 200),
  -- Bounded because the roster and prompts are re-sent to the Supervisor on
  -- every turn: unbounded text here multiplies directly into token cost.
  system_prompt text not null check (length(btrim(system_prompt)) between 1 and 8000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists agents_creator_id_idx on public.agents (creator_id);

drop trigger if exists agents_set_updated_at on public.agents;
create trigger agents_set_updated_at
  before update on public.agents
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- rooms — one roundtable session working toward one objective
-- ---------------------------------------------------------------------------

create table if not exists public.rooms (
  id uuid primary key default gen_random_uuid(),
  creator_id uuid not null references public.users (id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 200),
  objective text not null check (length(btrim(objective)) between 1 and 4000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists rooms_creator_id_idx on public.rooms (creator_id);

drop trigger if exists rooms_set_updated_at on public.rooms;
create trigger rooms_set_updated_at
  before update on public.rooms
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- room_agents — which workers sit at which roundtable
--
-- A join table rather than an array column on rooms: the roster is queried in
-- both directions (agents in a room, rooms using an agent) and an array
-- supports neither with an index.
-- ---------------------------------------------------------------------------

create table if not exists public.room_agents (
  room_id uuid not null references public.rooms (id) on delete cascade,
  agent_id uuid not null references public.agents (id) on delete cascade,
  added_at timestamptz not null default now(),
  primary key (room_id, agent_id)
);

-- The primary key already indexes room_id as its leading column; agent_id
-- needs its own index for the reverse lookup and for cascade deletes.
create index if not exists room_agents_agent_id_idx on public.room_agents (agent_id);

-- ---------------------------------------------------------------------------
-- messages — the Supervisor's context memory, replayed on every turn
-- ---------------------------------------------------------------------------

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  -- Monotonic insert order. created_at can tie between a supervisor decision
  -- and the agent message it triggers, and a transcript that replays in the
  -- wrong order misrepresents who acted when. seq breaks those ties.
  seq bigint generated always as identity,
  room_id uuid not null references public.rooms (id) on delete cascade,
  emitter text not null check (emitter in ('user', 'agent', 'supervisor', 'system')),
  emitter_name text not null check (length(btrim(emitter_name)) between 1 and 100),
  content text not null,
  created_at timestamptz not null default now()
);

-- The only access pattern: replay one room's transcript in order. Ordering by
-- seq rather than created_at makes this deterministic, so a separate
-- (room_id, created_at) index would be redundant write cost.
create index if not exists messages_room_id_seq_idx on public.messages (room_id, seq);

-- ---------------------------------------------------------------------------
-- usage_events — what each provider request actually cost
--
-- Recording is not deferred even though billing is. Phase 1 metrics depend on
-- this table existing from the first migration.
-- ---------------------------------------------------------------------------

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users (id) on delete cascade,
  -- Usage outlives the room and message it came from: deleting a room must not
  -- erase the record of money already spent.
  room_id uuid references public.rooms (id) on delete set null,
  message_id uuid references public.messages (id) on delete set null,
  model text not null,
  prompt_tokens integer not null default 0 check (prompt_tokens >= 0),
  completion_tokens integer not null default 0 check (completion_tokens >= 0),
  -- The provider's reported cost, stored untouched. Null means the provider
  -- did not report one. Six decimal places because a single call can cost a
  -- small fraction of a cent.
  cost_usd numeric(12, 6) check (cost_usd >= 0),
  is_priced boolean not null default false,
  provider_generation_id text,
  created_at timestamptz not null default now(),

  -- Enforces the rule that an unpriced request is never recorded as free.
  -- Writing zero for a missing cost silently understates what was spent, so
  -- the database refuses the row rather than trusting the application.
  constraint usage_events_priced_xor_null check (
    (is_priced and cost_usd is not null) or (not is_priced and cost_usd is null)
  )
);

create index if not exists usage_events_user_id_created_at_idx
  on public.usage_events (user_id, created_at);
create index if not exists usage_events_room_id_idx on public.usage_events (room_id);
create index if not exists usage_events_message_id_idx on public.usage_events (message_id);

-- Surfaces the unpriced-request ceiling cheaply without scanning the table.
create index if not exists usage_events_unpriced_idx
  on public.usage_events (user_id, created_at)
  where not is_priced;
