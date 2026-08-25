-- =====================================================================
-- Schema aislado. Diseñado para convivir con un proyecto Supabase que ya
-- tiene cosas adentro: nada toca `public` salvo la función del 02.
--
-- PostgREST solo expone los schemas listados en Settings > API > Exposed
-- schemas (por defecto `public`). Al dejar la tabla en `cc`, que NO está
-- expuesto, la tabla es inalcanzable por REST por construcción, no por
-- policy. El RLS de abajo es la segunda capa, no la única.
-- =====================================================================

create schema if not exists cc;

create table if not exists cc.partidas (
    id                      bigint generated always as identity primary key,
    proveedor_id            text        not null,
    clave_referencia        text,
    referencia              text,
    documento               text,
    clave_referencia_1      text,
    via_pago                text,
    bloqueo_pago            text,
    dias_vencida            integer,
    importe_documento       numeric(18,2),
    moneda_documento        text,
    importe_local           numeric(18,2),
    moneda_local            text,
    fecha_documento         date,
    fecha_contabilizacion   date,
    fecha_vencimiento       date,
    fecha_compensacion      date,
    documento_compensacion  text,
    clase_documento         text,
    cuenta_contrapartida    text
);

create index if not exists partidas_proveedor_idx
    on cc.partidas (proveedor_id);

create index if not exists partidas_abiertas_idx
    on cc.partidas (proveedor_id, fecha_vencimiento)
    where fecha_compensacion is null;

-- Segunda capa. Si alguien agrega `cc` a los exposed schemas, sigue cerrado.
alter table cc.partidas enable row level security;

-- El schema `cc` NUNCA se le concede a anon. Esa es la defensa principal.
revoke all on schema cc from anon, authenticated;
revoke all on cc.partidas from anon, authenticated;

-- Necesario solo para que anon pueda RESOLVER la función del 02, que vive
-- en public. Idempotente: los proyectos nuevos (desde 2026) exigen grants
-- explícitos para la Data API; sin USAGE el RPC devuelve 404.
grant usage on schema public to anon, authenticated;