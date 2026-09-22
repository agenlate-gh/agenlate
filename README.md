# Agenlate

Agenlate lets anyone build a team of AI workers by describing them in plain English, give that team a goal, and watch them work on it together in real time. A Supervisor agent decides which worker acts on each turn and why, so the process is visible rather than a black box. No coding, no node diagrams, no subscription — users bring their own OpenRouter key.

## Layout

```
backend/              FastAPI service — Supervisor, roundtable orchestration, usage recording
frontend/             Next.js + TypeScript + Tailwind, deployed on Vercel
supabase/migrations/  SQL schema and row-level security policies
CLAUDE.md             Context and invariants for AI coding agents — read this first
```

Monorepo. Deployed as two Render services from this one repository: a Web Service rooted at `backend/` and a Static Site rooted at `frontend/`.

## Running locally

Both halves need their own environment file. Copy the examples and fill them in:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn agenlate.main:create_app --factory --reload      # http://localhost:8000
pytest                                                    # runs with no API key and no network
```

**Frontend**

```bash
cd frontend
pnpm install
pnpm dev                                                  # http://localhost:3000
```

**Database**

Migrations live in `supabase/migrations/`. See `supabase/README.md` for how to apply them.

## A note on keys

Users supply their own OpenRouter API key. It is stored in their browser and sent per-run over TLS; the backend holds it in memory for the duration of that run and then discards it. It is never written to the database, to disk, or to logs.

The Supabase service-role key is backend-only — it bypasses row-level security, so it must never appear anywhere under `frontend/`.

## Deploying

`render.yaml` describes the services, so they can be recreated rather than
remembered. Secrets are marked `sync: false`: Render prompts for them in the
dashboard and never reads them from the file, which is why the file is
committable.

**First deploy**

1. In Render, create a Blueprint from this repository. It picks up
   `render.yaml` and proposes the `agenlate-api` web service.
2. Supply the values Render asks for: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`, and `API_CORS_ORIGINS`.
3. Deploy, then check `https://<service>.onrender.com/health`.

`API_CORS_ORIGINS` must name the deployed frontend origin. Production refuses a
wildcard — the application will not start with one — so this cannot be left
permissive by accident.

**What the free tier means in practice**

The service sleeps after 15 minutes without traffic and takes about a minute to
wake. The first visitor after a quiet period waits through that. A request every
10 minutes to `/health` prevents it, and fits inside the 750 monthly instance
hours — but only just, and only for one service, so there is no room for a
second always-on process.

The filesystem is ephemeral. Nothing may be written to disk; all state is in
Supabase.

**Running the frontend**

The frontend will deploy as a static site. Those are free, never sleep, and are
served from a CDN. It is absent from `render.yaml` until its stack is settled.

## Status

Phase 1, MVP build. See `CLAUDE.md` for architecture and the invariants that govern changes here.
