-- Aggregate usage for the Phase 1 metrics.
--
-- A database function rather than fetching rows and summing them in Python.
-- Token volume is one of the numbers the pre-seed pitch rests on, and by the
-- time it is worth showing there will be far too many rows to pull across the
-- wire to add up.
--
-- SECURITY INVOKER, so the function runs as the caller and row-level security
-- applies exactly as it does to a direct query. A SECURITY DEFINER version
-- would happily aggregate every user's spending for whoever asked.

create or replace function public.usage_summary(
  p_from timestamptz default null,
  p_to timestamptz default null,
  p_room_id uuid default null
)
returns table (
  total_requests bigint,
  priced_requests bigint,
  unpriced_requests bigint,
  prompt_tokens bigint,
  completion_tokens bigint,
  total_tokens bigint,
  cost_usd numeric,
  server_tool_calls bigint,
  rooms_touched bigint,
  first_at timestamptz,
  last_at timestamptz
)
language sql
security invoker
stable
set search_path = ''
as $$
  select
    count(*)::bigint,
    count(*) filter (where u.is_priced)::bigint,
    count(*) filter (where not u.is_priced)::bigint,
    coalesce(sum(u.prompt_tokens), 0)::bigint,
    coalesce(sum(u.completion_tokens), 0)::bigint,
    coalesce(sum(u.prompt_tokens + u.completion_tokens), 0)::bigint,
    -- Sums only what was actually reported. Unpriced requests are counted
    -- separately rather than folded in as zero, so a total is never quietly
    -- understated by requests nobody priced.
    coalesce(sum(u.cost_usd), 0)::numeric,
    coalesce(sum(u.server_tool_calls), 0)::bigint,
    count(distinct u.room_id)::bigint,
    min(u.created_at),
    max(u.created_at)
  from public.usage_events u
  where (p_from is null or u.created_at >= p_from)
    and (p_to is null or u.created_at < p_to)
    and (p_room_id is null or u.room_id = p_room_id);
$$;

revoke execute on function public.usage_summary(timestamptz, timestamptz, uuid) from public, anon;
grant execute on function public.usage_summary(timestamptz, timestamptz, uuid) to authenticated;
