"""Tool de LangGraph sobre el RPC de Supabase.

El modelo ve un contrato tipado, nunca PostgREST crudo: si le dás la tabla,
tiene que construir `?proveedor_id=eq.0000123456&fecha_compensacion=is.null`
y la regla de negocio (abierta = sin compensar) queda del lado del LLM.
"""
import os

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]          # https://<ref>.supabase.co
SUPABASE_KEY = os.environ["SUPABASE_PUBLISHABLE_KEY"]   # sb_publishable_... -> rol anon
RPC = f"{SUPABASE_URL}/rest/v1/rpc/cuenta_corriente_proveedor"
TIMEOUT = 20

# Solo el header `apikey`. Las claves sb_publishable_/sb_secret_ NO son JWT:
# mandarlas en `Authorization: Bearer` hace que el gateway intente parsearlas
# como JWT y rechace el request.
_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Content-Type": "application/json",
}


class CuentaCorrienteInput(BaseModel):
    proveedor_id: str = Field(
        description="Número de acreedor SAP. Se normaliza a 10 dígitos con ceros a izquierda."
    )
    solo_abiertas: bool = Field(
        default=True, description="True = solo partidas sin fecha de compensación."
    )
    solo_vencidas: bool = Field(
        default=False, description="True = solo partidas con vencimiento anterior a hoy."
    )
    incluir_partidas: bool = Field(
        default=False,
        description="True SOLO si el usuario pide el detalle documento por documento. "
                    "Para saldos, totales o aging dejar en False.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Tope de filas de detalle.")


@tool("consultar_cuenta_corriente_proveedor", args_schema=CuentaCorrienteInput)
def consultar_cuenta_corriente_proveedor(
    proveedor_id: str,
    solo_abiertas: bool = True,
    solo_vencidas: bool = False,
    incluir_partidas: bool = False,
    limit: int = 50,
) -> dict:
    """Devuelve saldos por moneda, aging por tramo de vencimiento y opcionalmente
    el detalle de partidas de la cuenta corriente de un proveedor.

    cantidad_partidas = 0 significa que el acreedor EXISTE pero no tiene partidas
    bajo esos filtros. El acreedor inexistente devuelve {"error": "acreedor_inexistente"}.
    No confundir ambos casos.
    """
    payload = {
        "p_proveedor_id": proveedor_id,
        "p_solo_abiertas": solo_abiertas,
        "p_solo_vencidas": solo_vencidas,
        "p_incluir_partidas": incluir_partidas,
        "p_limit": limit,
    }
    r = httpx.post(RPC, json=payload, headers=_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


TOOLS = [consultar_cuenta_corriente_proveedor]
