-- =====================================================================
-- Única superficie expuesta. Vive en `public` (schema expuesto por PostgREST)
-- pero lee de `cc` (no expuesto), corriendo como owner.
--   POST /rest/v1/rpc/cuenta_corriente_proveedor
-- =====================================================================

create or replace function public.cuenta_corriente_proveedor(
    p_proveedor_id      text,
    p_solo_abiertas     boolean default true,
    p_solo_vencidas     boolean default false,
    p_incluir_partidas  boolean default false,
    p_limit             integer default 50
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''      -- todo calificado. Cierra el search_path hijacking.
as $$
declare
    v_id      text    := pg_catalog.lpad(pg_catalog.btrim(p_proveedor_id), 10, '0');
    v_limit   integer := least(greatest(coalesce(p_limit, 50), 1), 200);
    v_existe  boolean;
    v_total   integer;
    v_result  jsonb;
begin
    select exists(select 1 from cc.partidas where proveedor_id = v_id)
      into v_existe;

    if not v_existe then
        return jsonb_build_object(
            'error', 'acreedor_inexistente',
            'proveedor_id', v_id
        );
    end if;

    with filtrado as (
        select *,
               case when fecha_compensacion is null then 'abierta' else 'compensada' end as estado
          from cc.partidas
         where proveedor_id = v_id
           and (not p_solo_abiertas or fecha_compensacion is null)
           and (not p_solo_vencidas
                or (fecha_vencimiento is not null and fecha_vencimiento < current_date))
    ),
    tramos as (
        select case
                   when fecha_vencimiento is null              then 'sin_vencimiento'
                   when fecha_vencimiento >= current_date      then 'por_vencer'
                   when current_date - fecha_vencimiento <= 30 then '0_30'
                   when current_date - fecha_vencimiento <= 60 then '31_60'
                   when current_date - fecha_vencimiento <= 90 then '61_90'
                   else                                             'mas_90'
               end as tramo,
               moneda_local,
               importe_local
          from filtrado
    ),
    saldos_doc as (
        select jsonb_agg(jsonb_build_object('moneda', moneda_documento, 'saldo', saldo)
                         order by moneda_documento) as j
          from (
              select moneda_documento, sum(importe_documento) as saldo
                from filtrado
               where moneda_documento is not null
               group by moneda_documento
          ) s
    ),
    saldos_loc as (
        select jsonb_agg(jsonb_build_object('moneda', moneda_local, 'saldo', saldo)
                         order by moneda_local) as j
          from (
              select moneda_local, sum(importe_local) as saldo
                from filtrado
               where moneda_local is not null
               group by moneda_local
          ) s
    ),
    aging as (
        select jsonb_agg(jsonb_build_object(
                   'tramo', tramo, 'cantidad', cantidad, 'saldo', saldo, 'moneda', moneda_local
               ) order by orden) as j
          from (
              select tramo, moneda_local, count(*) as cantidad, sum(importe_local) as saldo,
                     array_position(
                         array['por_vencer','0_30','31_60','61_90','mas_90','sin_vencimiento'],
                         tramo
                     ) as orden
                from tramos
               group by tramo, moneda_local
          ) t
    ),
    detalle as (
        select case when p_incluir_partidas then
                   coalesce(jsonb_agg(to_jsonb(d) - 'estado' - 'id'
                                      order by d.fecha_vencimiento nulls last), '[]'::jsonb)
               else null end as j
          from (
              select * from filtrado
               order by fecha_vencimiento nulls last
               limit v_limit
          ) d
    )
    select
        jsonb_strip_nulls(jsonb_build_object(
            'proveedor_id',            v_id,
            'cantidad_partidas',       (select count(*) from filtrado),
            'filtros',                 jsonb_build_object(
                                           'solo_abiertas', p_solo_abiertas,
                                           'solo_vencidas', p_solo_vencidas
                                       ),
            'saldos_moneda_documento', coalesce((select j from saldos_doc), '[]'::jsonb),
            'saldos_moneda_local',     coalesce((select j from saldos_loc), '[]'::jsonb),
            'aging',                   coalesce((select j from aging), '[]'::jsonb),
            'partidas',                (select j from detalle)
        )),
        (select count(*) from filtrado)
      into v_result, v_total;

    if p_incluir_partidas then
        v_result := v_result || jsonb_build_object('partidas_truncadas', v_total > v_limit);
    end if;

    return v_result;
end;
$$;

-- Postgres concede EXECUTE a PUBLIC por defecto. Revocar y conceder explícito.
revoke execute on function public.cuenta_corriente_proveedor(text, boolean, boolean, boolean, integer)
    from public;

grant execute on function public.cuenta_corriente_proveedor(text, boolean, boolean, boolean, integer)
    to anon, authenticated;