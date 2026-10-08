-- Trial uses: the few runs a new account gets on Agenlate's own key.
--
-- A new user otherwise has to open an OpenRouter account and paste a key
-- before anything happens, and most stop there. So a new account gets a small
-- number of runs paid by us, plus the short helper calls (the agent builder
-- and the objective writer) that lead up to a run.
--
-- Every use is a row, and the limits are counts of rows: so many per account,
-- so many in total. The total is what bounds the bill, so it is checked in the
-- same transaction as the insert, under a lock, rather than read first and
-- written after.
--
-- Only the backend touches this table, through the service role. A use that a
-- browser could insert or delete would be a limit the browser sets for itself.

create table if not exists public.trial_uses (
  id uuid primary key default gen_random_uuid(),

  -- Kept when the account is deleted. The money was spent either way, and a
  -- row that vanished with its account would quietly raise the total.
  user_id uuid references auth.users (id) on delete set null,

  -- 'run' is a whole roundtable. 'assist' is one turn of the agent builder or
  -- the objective writer: a single short call, counted separately because a
  -- person takes many of them on the way to one run.
  kind text not null check (kind in ('run', 'assist')),

  -- Which room a run was for. No foreign key: the record outlives the room.
  room_id uuid,

  created_at timestamptz not null default now()
);

create index if not exists trial_uses_user_kind_idx
  on public.trial_uses (user_id, kind);

alter table public.trial_uses enable row level security;
alter table public.trial_uses force row level security;

revoke all on public.trial_uses from anon, authenticated;

comment on table public.trial_uses is
  'Runs and helper calls paid from Agenlate''s own key. Service role only.';

-- Take one use if both limits allow it.
--
-- One lock for the whole table rather than one per account: the total is
-- shared, so two accounts claiming the last place must not both get it. The
-- volume is a few hundred rows over the Beta, so the lock is never contended
-- for long.
create or replace function public.claim_trial_use(
  p_user_id uuid,
  p_kind text,
  p_room_id uuid,
  p_user_limit integer,
  p_total_limit integer
)
returns table (outcome text, remaining integer, use_id uuid)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_used integer;
  v_total integer;
  v_id uuid;
begin
  perform pg_advisory_xact_lock(hashtext('public.trial_uses'));

  select count(*) into v_used
    from public.trial_uses t
   where t.user_id = p_user_id and t.kind = p_kind;

  if v_used >= p_user_limit then
    return query select 'user_limit'::text, 0, null::uuid;
    return;
  end if;

  select count(*) into v_total
    from public.trial_uses t
   where t.kind = p_kind;

  if v_total >= p_total_limit then
    return query select 'total_limit'::text, 0, null::uuid;
    return;
  end if;

  insert into public.trial_uses (user_id, kind, room_id)
  values (p_user_id, p_kind, p_room_id)
  returning id into v_id;

  return query select 'claimed'::text, p_user_limit - v_used - 1, v_id;
end;
$$;

revoke all on function public.claim_trial_use(uuid, text, uuid, integer, integer)
  from public, anon, authenticated;
grant execute on function public.claim_trial_use(uuid, text, uuid, integer, integer)
  to service_role;
