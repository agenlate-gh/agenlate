-- Keep the API awake.
--
-- Render's free plan stops the API after about fifteen minutes without a
-- request, and the next request waits up to a minute while it starts again.
-- For a new user that minute is the first impression: deleting a room took
-- forty seconds in testing, and a first sign-in can look like a failure.
--
-- A request every ten minutes keeps it running. It is sent from here rather
-- than from a separate monitoring service so that it lives with the rest of
-- the deployment and needs no further account. One free service running all
-- month uses about 744 hours, inside Render's 750 free hours per workspace —
-- a second always-on free service would not fit, so revisit this if one is
-- added.

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Replaced rather than duplicated if this migration is applied again.
select cron.unschedule('keep-api-awake')
where exists (select 1 from cron.job where jobname = 'keep-api-awake');

select cron.schedule(
  'keep-api-awake',
  '*/10 * * * *',
  $$ select net.http_get(
       url := 'https://agenlate-api.onrender.com/health',
       timeout_milliseconds := 60000
     ) $$
);
