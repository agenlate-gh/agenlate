# CLAUDE.md

Context for AI coding agents working in this repository. Read this before writing code.

## What Agenlate is

A platform where non-technical users design AI "worker" agents in natural language, assign them a shared objective, and watch them collaborate in a supervised roundtable. A Supervisor agent decides which worker acts on each turn by returning a structured JSON decision.

Three layers:

1. **Natural Language Builder** (`frontend/`) — users describe the workers they want and state an objective.
2. **Supervisor** (`backend/src/agenlate/supervisor/`) — parses the objective, evaluates the agent roster, and dictates turn order by emitting a validated JSON decision. It exists specifically to prevent infinite loops, hallucinated dispatches, and token waste.
3. **Roundtable** (`backend/src/agenlate/orchestrator.py`) — runs the loop, executes agents, persists messages, records usage.

The Supervisor's structured-output contract is the architectural heart. Everything else feeds it context or acts on its decisions.

## Layout

```
backend/     FastAPI, Python 3.11+, fully async
frontend/    React + Vite + TypeScript + Tailwind
supabase/    SQL migrations
```

Monorepo. Deployed as two Render services: a Web Service (`backend/`) and a Static Site (`frontend/`), each with its own Root Directory and build filter.

## Invariants

These are decisions, not preferences. Do not revert them while "improving" adjacent code. If one seems wrong, raise it rather than working around it.

### Secrets

- The user's OpenRouter key is **never persisted**. Not to Supabase, not to disk, not to logs, not into an exception message or traceback. It lives in backend memory for the duration of one run and is then dropped.
- Users bring their own key (BYOK). It is stored in their browser's `localStorage` and sent per-run over TLS. There is no "temporary" database column for it and no cache.
- `SUPABASE_SERVICE_ROLE_KEY` is **backend-only**. Vite inlines env vars into the public bundle at build time, so anything under `frontend/` is world-readable. The frontend gets the Supabase URL, the anon key, and the API base URL — nothing else.
- Anything holding a secret masks it in `__repr__`. A logging filter redacts key-shaped strings from every log record.

### Money

- The billing meter reads **the cost OpenRouter reports** in the response `usage` object. It never computes a price from token counts.
  Why: OpenRouter bills some things per call rather than per token (server tools), so token-derived pricing silently misses real cost and breaks on every future pricing change.
- Missing cost is recorded as `is_priced=False` with a null cost. **Never zero.**
- Provider figures are stored untouched. Margin is applied downstream and never mutates the recorded original.
- The margin function exists but is **not wired into anything**. Billing is deferred to Phase 2; usage *recording* is not.

### Architecture

- The Supervisor, orchestrator, and billing layers depend only on the `LLMClient` protocol. Nothing in them imports anything OpenRouter-specific.
  Why: the seam is cheap to keep and expensive to retrofit. It is not an invitation to add providers — OpenRouter is the only implementation in the MVP.
- Agent sandboxing uses **OpenRouter server tools** (`openrouter:web_search`, `openrouter:web_fetch`, sandboxed bash). Do not build a sandbox.
- The Render backend filesystem is **ephemeral**. No SQLite, no local files, no on-disk session state. All state is in Supabase.
- Row-level security is on for every table. Users read and write only their own rows. Backend requests carry the user's JWT so RLS applies; `service_role` is for genuinely privileged operations only, documented at each call site.

### Correctness

- Every run must terminate for a **named reason**: completed, max turns, spend cap, stalled, no progress, unpriced ceiling, provider failure, or user cancellation. "It stopped" is not an acceptable outcome.
- Supervisor output is validated against a closed schema. On failure, retry with a repair prompt (bounded), then **fail closed**. Never fall back to a guessed decision.
- Usage from repair attempts counts. Repairs cost real money.

## Conventions

- Async throughout the backend. Type hints on everything public.
- Explicit pydantic request/response schemas at the API boundary. Never return raw database rows.
- Tests run with **no API key and no network**. `FakeLLM` drives the LLM paths; `respx` covers the HTTP client.
- Frontend types are generated from the backend's OpenAPI schema and committed. Regenerate rather than hand-editing.
- No ORM. Focused async repository functions per table.

## Commands

```bash
# backend
cd backend && uvicorn agenlate.main:create_app --factory --reload
cd backend && pytest

# frontend
cd frontend && npm run dev
cd frontend && npm run build

# regenerate API types
cd frontend && npm run gen:types
```

## Data model

Five tables. `users`, `agents`, `rooms`, `room_agents` (join), `messages`, plus `usage_events`.

`messages` is the Supervisor's context memory and is replayed on every turn, so its size directly drives cost — the prompt builder windows it rather than sending everything.

`usage_events` records what each request cost. It exists from the first migration because Phase 1 metrics depend on it, even though billing ships in Phase 2.

## When something is ambiguous

Prefer the choice that is easier to reverse. Flag the ambiguity rather than inventing a requirement — the scope is deliberately narrow and additions are usually out of scope by decision, not oversight.
