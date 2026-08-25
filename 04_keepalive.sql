-- OPCIONAL y solo en plan Free: se pausa el proyecto tras 7 días sin actividad
-- de base. Si el proyecto que reusás ya tiene tráfico, no hace falta.
create extension if not exists pg_cron;

select cron.schedule(
    'keepalive-cc',
    '0 12 * * 1,4',                          -- lunes y jueves 12:00 UTC
    $$select count(*) from cc.partidas$$
);

-- select * from cron.job;
-- select cron.unschedule('keepalive-cc');