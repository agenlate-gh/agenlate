-- Per-agent tool permissions, and a record of server tool usage.

-- Which OpenRouter server tools an agent may call.
--
-- NULL means every tool, rather than none. A user creating an agent without
-- thinking about tools should get a capable one; opting out is the deliberate
-- act, not opting in.
alter table public.agents
  add column if not exists enabled_tools text[] default null;

-- How many server tool steps a request consumed.
--
-- OpenRouter reports these as counts in usage.server_tool_use, separately from
-- the token figures, and web search is priced per result rather than per token.
-- Whether those charges are already inside the reported cost is not documented,
-- so the count is recorded alongside it. With both, the question can be settled
-- from real data instead of assumed: if tool calls rise while cost does not,
-- the meter is missing spending.
alter table public.usage_events
  add column if not exists server_tool_calls integer not null default 0
    check (server_tool_calls >= 0);

-- Finds requests that used tools, for comparing cost against tool volume.
create index if not exists usage_events_with_tools_idx
  on public.usage_events (user_id, created_at)
  where server_tool_calls > 0;
