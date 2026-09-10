-- Revoke public EXECUTE on the rls_auto_enable event trigger function.
--
-- public.rls_auto_enable() backs the `ensure_rls` event trigger, which enables
-- row-level security on any new table in the public schema. It was already
-- present in the project rather than created by these migrations.
--
-- The problem is not what it does but who can reach it: it is SECURITY DEFINER
-- and EXECUTE was never revoked, so PostgREST exposes it at
-- /rest/v1/rpc/rls_auto_enable to anon and authenticated alike. Supabase's own
-- database linter flags this (lints 0028 and 0029).
--
-- Revoking is safe. An event trigger runs with the privileges of its owner and
-- does not consult the caller's EXECUTE privilege, so `ensure_rls` keeps firing
-- on CREATE TABLE exactly as before.

do $$
begin
  if exists (
    select 1
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'rls_auto_enable'
  ) then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end $$;
