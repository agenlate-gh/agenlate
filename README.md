# Agenlate

Agenlate lets anyone build a team of AI workers by describing them in plain English, give that team a goal, and watch them work on it together in real time. A Supervisor agent decides which worker acts on each turn and why, so the process is visible rather than a black box. No coding, no node diagrams, no subscription — users bring their own OpenRouter key.

## Layout

```
backend/              FastAPI service — Supervisor, roundtable orchestration, usage recording
frontend/             React + Vite + TypeScript + Tailwind
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
uvicorn agenlate.main:app --reload                       # http://localhost:8000
pytest                                                    # runs with no API key and no network
```

**Frontend**

```bash
cd frontend
npm install
npm run dev                                               # http://localhost:5173
```

**Database**

Migrations live in `supabase/migrations/`. See `supabase/README.md` for how to apply them.

## A note on keys

Users supply their own OpenRouter API key. It is stored in their browser and sent per-run over TLS; the backend holds it in memory for the duration of that run and then discards it. It is never written to the database, to disk, or to logs.

The Supabase service-role key is backend-only — it bypasses row-level security, so it must never appear anywhere under `frontend/`.

## Status

Phase 1, MVP build. See `CLAUDE.md` for architecture and the invariants that govern changes here.
