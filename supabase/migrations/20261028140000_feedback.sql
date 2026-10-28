-- What Beta users tell us from inside the product.
--
-- Two questions we want answered by everyone who tries Agenlate — what they
-- would automate, and which tools they would connect — plus room for anything
-- else. One row per answer, tagged with the question, so the answers to each
-- can be read and counted on their own: that count is a Beta metric, and the
-- "connect" answers decide which integration comes first.
--
-- A user can add their own answers and nothing else. Reading them is done
-- with the service role, from the admin command.

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),

  -- Kept if the account is deleted: what someone told us is still worth having.
  user_id uuid references auth.users (id) on delete set null,

  question text not null check (question in ('automate', 'connect', 'general')),
  answer text not null check (length(btrim(answer)) between 1 and 2000),

  -- Where in the app they were when they wrote it, e.g. "/rooms/…".
  page text check (page is null or length(page) <= 200),

  created_at timestamptz not null default now()
);

create index if not exists feedback_created_at_idx on public.feedback (created_at desc);
create index if not exists feedback_user_id_idx on public.feedback (user_id);

alter table public.feedback enable row level security;
alter table public.feedback force row level security;

revoke all on public.feedback from anon, authenticated;
grant insert on public.feedback to authenticated;

drop policy if exists feedback_insert_own on public.feedback;
create policy feedback_insert_own on public.feedback
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

comment on table public.feedback is
  'Answers from Beta users. Users insert their own; only the service role reads.';
