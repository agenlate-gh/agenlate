# Database

Postgres 17 on Supabase. Schema and row-level security live in `migrations/`, applied in filename order.

## Applying migrations

Migrations are plain SQL, named `YYYYMMDDHHMMSS_description.sql`. Every one is written to be idempotent — `create table if not exists`, `drop policy if exists` before `create policy`, and `do $$ ... $$` guards around anything Postgres cannot express as `if not exists` — so re-running a migration is safe.

**Via the Supabase CLI** (preferred once installed):

```bash
supabase link --project-ref <project-ref>
supabase db push
```

**Via the dashboard**: paste each file into the SQL Editor in filename order.

**Via the Supabase MCP server**: `apply_migration`, one file per call, in filename order.

## Tables

| Table | Purpose |
|---|---|
| `users` | Application row mirroring `auth.users`, plus the Phase 2 credit balance |
| `agents` | A user-designed worker profile |
| `rooms` | One roundtable session working toward one objective |
| `room_agents` | Which workers sit at which roundtable |
| `messages` | The transcript, and the Supervisor's context memory |
| `usage_events` | What each provider request actually cost |

Two details worth knowing before writing queries against them:

**`messages.seq`** is a monotonic identity column. Order transcripts by `seq`, not `created_at` — a supervisor decision and the agent message it triggers can land in the same instant, and a transcript that replays out of order misrepresents who acted when.

**`usage_events` is append-only.** `authenticated` holds `select` and `insert` and nothing else, so a user cannot rewrite their own record of what was spent. A check constraint enforces that `is_priced` and `cost_usd` agree: a request with no reported cost is stored with a null cost, never zero. Recording a missing cost as free would silently understate spending, so the database refuses the row rather than trusting the caller.

## Row-level security

Every table has RLS enabled and forced. `anon` is granted nothing. `authenticated` reaches only its own rows; `messages` and `room_agents` are scoped through the room that owns them.

Policies wrap the identity call as `(select auth.uid())` rather than calling `auth.uid()` bare. The bare form is re-evaluated once per row; wrapped in a subquery, Postgres evaluates it once and caches it.

`force row level security` is set so the policies apply to the table owner as well. `postgres` and `service_role` hold `BYPASSRLS`, so the backend and the dashboard are unaffected — but table ownership alone stops being a way around the policies.

### Verifying policies

Policies are not self-evidently correct and should be re-verified whenever they change. Impersonate a user in a single transaction:

```sql
begin;
  select set_config('request.jwt.claims', '{"sub":"<user-uuid>","role":"authenticated"}', true);
  select set_config('role', 'authenticated', true);

  select count(*) from public.rooms;   -- only this user's rooms
rollback;
```

The suite run against this schema covers thirteen negative cases — cross-user reads of rooms, agents, transcripts, the usage ledger, the user row and the roster; writing into another user's room; attaching another user's agent to your own room; forging usage against another account; rewriting your own ledger; updating and deleting another user's room — plus a positive control confirming a user can still see their own data, and a check that an unpriced request cannot be stored as zero cost.

A suite where everything is denied passes for the wrong reason. Keep the positive control.

## After changing the schema

Run Supabase's linter and treat warnings as work, not noise:

```
get_advisors(type='security')
get_advisors(type='performance')
```

The security linter catches missing RLS policies and `SECURITY DEFINER` functions exposed over the REST API — the two failures most likely to leak data and least likely to be noticed.
