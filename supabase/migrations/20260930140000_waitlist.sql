-- The waitlist: people who asked to join the Beta and have no invite yet.
--
-- The landing page is public, so this table fills from the open internet. Like
-- invite_codes it has no policies and no grants to browser roles: the list of
-- people who asked is personal data, and nothing in the browser needs to read
-- it. The backend writes it with the service role and an admin command reads
-- it back when invites go out.

create table if not exists public.waitlist (
  id bigint generated always as identity primary key,

  -- Stored lowercased by the backend, and unique, so asking twice is one entry
  -- rather than two. Length capped at the RFC 5321 maximum.
  email text not null unique
    check (length(email) between 3 and 254 and email = lower(email)),

  -- Where the signup came from: "landing" for now; a campaign or partner
  -- later, so it is possible to tell which channel people arrive through.
  source text not null default 'landing'
    check (length(btrim(source)) between 1 and 50),

  created_at timestamptz not null default now(),

  -- Set when an invite code is sent to this person, so the list shows who is
  -- still waiting.
  invited_at timestamptz
);

-- The admin command lists the queue oldest first.
create index if not exists waitlist_created_at_idx on public.waitlist (created_at);

alter table public.waitlist enable row level security;
alter table public.waitlist force row level security;

revoke all on public.waitlist from anon, authenticated;

comment on table public.waitlist is
  'Beta waitlist from the landing page. Service role only: no policies, no client grants.';
