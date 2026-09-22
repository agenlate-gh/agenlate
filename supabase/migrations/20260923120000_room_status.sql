-- Whether a room will accept a new run.
--
-- A room is a standing arrangement of agents, not a one-off job, so "stop
-- spending money on this one for now" has to be expressible without deleting
-- it and losing the transcript. Pausing is that.
--
-- A text column with a check constraint rather than a Postgres enum: adding a
-- value to an enum is a migration that cannot run inside a transaction with
-- other statements, and this list is likely to grow (archived, at least).
alter table public.rooms
  add column if not exists status text not null default 'active'
    check (status in ('active', 'paused'));

-- The lobby lists a user's rooms newest first and shows the state of each; the
-- creator_id index already covers the filter, and status is small enough that
-- a separate index would never be chosen.
comment on column public.rooms.status is
  'active: runs may start. paused: the API refuses to start one.';
