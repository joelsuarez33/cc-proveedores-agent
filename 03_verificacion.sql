-- =====================================================================
-- Verificación. Correr DESPUÉS de 01_schema.sql, 02_rpc.sql y de la carga.
--
-- El SQL Editor de Supabase muestra solo el resultado de la ÚLTIMA sentencia
-- que se ejecuta. Corré UN BLOQUE POR VEZ (seleccionalo y Ctrl+Enter),
-- no el archivo entero.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1) Datos cargados.
--    Esperado: filas > 0, acreedores > 0.
-- ---------------------------------------------------------------------
select count(*) as filas,
       count(distinct proveedor_id) as acreedores
  from cc.partidas;


-- ---------------------------------------------------------------------
-- 2) Ceros a izquierda intactos.
--    Esperado: length = 10 en todas las filas. Si ves '123456' con
--    length 6, el import se hizo por la UI y rompió el tipo.
-- ---------------------------------------------------------------------
select proveedor_id, length(proveedor_id) as largo
  from cc.partidas
 limit 5;


-- ---------------------------------------------------------------------
-- 3) Config de PostgREST: qué schemas expone.
--    Buscá la línea pgrst.db_schemas=... -> debe decir
--    'public, graphql_public', SIN 'cc'.
--
--    Si no devuelve filas, la config está a nivel proyecto y no de rol:
--    verificalo por UI en Settings > API > Exposed schemas.
--
--    Nota: `show pgrst.db_schemas` NO funciona acá. Ese parámetro lo lee
--    el rol `authenticator`, no el rol del SQL Editor.
-- ---------------------------------------------------------------------
select unnest(setconfig) as config
  from pg_db_role_setting s
  join pg_roles r on r.oid = s.setrole
 where r.rolname = 'authenticator';


-- ---------------------------------------------------------------------
-- 4) EL BLOQUE QUE IMPORTA. Privilegio efectivo del rol anon, que es el
--    que usa la publishable key. Mide permisos reales, no configuración.
--    Esperado: false, false, true.
--    Si anon_ve_schema o anon_lee_tabla dan true, PARÁ y revisá el 01.
-- ---------------------------------------------------------------------
select has_schema_privilege('anon', 'cc', 'USAGE')           as anon_ve_schema,
       has_table_privilege('anon', 'cc.partidas', 'SELECT')  as anon_lee_tabla,
       has_function_privilege(
           'anon',
           'public.cuenta_corriente_proveedor(text,boolean,boolean,boolean,integer)',
           'EXECUTE')                                        as anon_ejecuta_rpc;


-- ---------------------------------------------------------------------
-- 5) RLS activo sobre la tabla (segunda capa).
--    Esperado: rls_activo = true, policies = 0.
-- ---------------------------------------------------------------------
select c.relrowsecurity as rls_activo,
       (select count(*) from pg_policies
         where schemaname = 'cc' and tablename = 'partidas') as policies
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'cc' and c.relname = 'partidas';


-- ---------------------------------------------------------------------
-- 6) El RPC devuelve JSON con un acreedor real.
--    Esperado: objeto con proveedor_id, cantidad_partidas,
--    saldos_moneda_local y aging.
-- ---------------------------------------------------------------------
select public.cuenta_corriente_proveedor(
           (select proveedor_id from cc.partidas limit 1),
           true, false, false, 5
       ) as respuesta;


-- ---------------------------------------------------------------------
-- 7) Acreedor inexistente: error tipado, NO excepción.
--    Esperado: {"error": "acreedor_inexistente", "proveedor_id": "0000000000"}
--    Si tira excepción, el agente va a alucinar sobre este caso.
-- ---------------------------------------------------------------------
select public.cuenta_corriente_proveedor('0000000000', true, false, false, 5) as respuesta;


-- ---------------------------------------------------------------------
-- 8) Reconciliación. Este total tiene que coincidir con lo que imprimió
--    el loader Y con la fila de total del Excel original.
--    Si no coincide, el limpiador descartó o rescató filas de más.
-- ---------------------------------------------------------------------
select moneda_local,
       count(*) as partidas,
       sum(importe_local) as total
  from cc.partidas
 group by moneda_local
 order by moneda_local;


-- ---------------------------------------------------------------------
-- 9) Sanidad del corte abierta/compensada, que es la regla de negocio
--    central del RPC.
-- ---------------------------------------------------------------------
select case when fecha_compensacion is null then 'abierta' else 'compensada' end as estado,
       count(*) as partidas,
       sum(importe_local) as total_local
  from cc.partidas
 group by 1
 order by 1;


-- ---------------------------------------------------------------------
-- 10) Higiene del proyecto existente: tablas en `public` SIN RLS, o sea
--     legibles por cualquiera que tenga la publishable key. No es parte
--     de esta implementación, pero ahora vas a distribuir esa key en un
--     proceso más. Revisá que lo que aparezca sea intencional.
--     Esperado: idealmente vacío.
-- ---------------------------------------------------------------------
select c.relname as tabla_publica_sin_rls
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public'
   and c.relkind = 'r'
   and not c.relrowsecurity
 order by 1;