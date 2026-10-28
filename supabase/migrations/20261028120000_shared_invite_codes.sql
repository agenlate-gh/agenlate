-- Invite codes that more than one person can use.
--
-- Codes were single-use, handed out one by one. That works for people we
-- invite personally and not at all for a post in a community: everyone who
-- reads it reaches a sign-up page they cannot pass. In the first week of
-- posting, nobody from outside signed up.
--
-- So a code now has a number of uses. Existing codes keep one, and behave
-- exactly as before. A code for a channel ("reddit", "discord") gets as many
-- as that channel should bring in, and the cap keeps the Beta the size it was
-- planned for. Which code each account used is already recorded on the
-- account (app_metadata.invite_code), so channels can still be counted.

alter table public.invite_codes
  add column if not exists max_uses integer not null default 1
    check (max_uses between 1 and 1000),
  add column if not exists use_count integer not null default 0
    check (use_count >= 0);

-- Codes already spent count as one use of one.
update public.invite_codes set use_count = 1 where claimed_at is not null and use_count = 0;

alter table public.invite_codes
  drop constraint if exists invite_codes_use_count_within_max;
alter table public.invite_codes
  add constraint invite_codes_use_count_within_max check (use_count <= max_uses);

comment on column public.invite_codes.max_uses is
  'How many accounts this code can create. 1 for a personal invite.';
comment on column public.invite_codes.claimed_at is
  'When the code was first used.';
comment on column public.invite_codes.claimed_by is
  'The first account the code created. Every account records its own code.';

-- Take one use of a code, if it has one left. One statement, so two people
-- signing up at the same moment cannot both take the last use.
create or replace function public.claim_invite_code(p_code text)
returns table (code text)
language sql
security invoker
set search_path = ''
as $$
  update public.invite_codes c
     set use_count = c.use_count + 1,
         claimed_at = coalesce(c.claimed_at, now())
   where c.code = p_code
     and c.use_count < c.max_uses
  returning c.code;
$$;

-- Give back a use taken for a signup that then failed. A code that ends up
-- unused again is free again.
create or replace function public.release_invite_code(p_code text)
returns table (code text)
language sql
security invoker
set search_path = ''
as $$
  update public.invite_codes c
     set use_count = greatest(c.use_count - 1, 0),
         claimed_at = case when c.use_count <= 1 and c.claimed_by is null then null else c.claimed_at end
   where c.code = p_code
     and c.use_count > 0
  returning c.code;
$$;

revoke all on function public.claim_invite_code(text) from public, anon, authenticated;
revoke all on function public.release_invite_code(text) from public, anon, authenticated;
grant execute on function public.claim_invite_code(text) to service_role;
grant execute on function public.release_invite_code(text) to service_role;
