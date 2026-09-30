-- Invite codes: how the Beta stays at the size it was planned for.
--
-- A signup cap alone is first come, first served: anyone who finds the URL
-- takes a place, including bots. A code decides who gets in. Issuing a fixed
-- number of codes is also the cap, so the one mechanism does both jobs, and
-- the label records which channel each user came from.
--
-- Only the backend touches this table, through the service role. There are no
-- policies and no grants to anon or authenticated: a code must never be
-- readable, listable or claimable from the browser, or the gate is decorative.

create table if not exists public.invite_codes (
  -- Twelve characters in groups of four, from an alphabet without the ones
  -- people misread (0/O, 1/I/L). 31^12 is about 10^18, so guessing one is not
  -- a practical attack even without a rate limit.
  code text primary key
    check (code ~ '^[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}$'),

  -- Where the code was handed out: "casa212", "discord", "andres". Free text,
  -- because the set of channels is not known in advance.
  label text check (label is null or length(btrim(label)) between 1 and 100),

  created_at timestamptz not null default now(),

  -- Set when a signup takes the code. A code stays spent even if the account
  -- is later deleted: re-issuing it would quietly raise the cap.
  claimed_at timestamptz,
  claimed_by uuid references auth.users (id) on delete set null,

  -- A code with an owner but no claim time would be neither free nor spent.
  constraint invite_codes_claim_consistent
    check (claimed_by is null or claimed_at is not null)
);

-- For "who used which code" and for the cascade when an account is deleted.
create index if not exists invite_codes_claimed_by_idx
  on public.invite_codes (claimed_by);

alter table public.invite_codes enable row level security;
alter table public.invite_codes force row level security;

revoke all on public.invite_codes from anon, authenticated;

comment on table public.invite_codes is
  'Beta invite codes. Service role only: no policies, no client grants.';
