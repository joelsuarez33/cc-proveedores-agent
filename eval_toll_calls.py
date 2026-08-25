"""Eval barato: mide si el modelo extrae bien los argumentos de la tool.

No pega contra Supabase — solo mide la decisión del modelo. Corre en segundos
y cuesta centavos. Es el único modo honesto de decidir si un cambio de
proveedor degrada o no.

    LLM_PROVIDER=anthropic python eval_tool_calls.py
    LLM_PROVIDER=deepseek  python eval_tool_calls.py
"""
import json
import os

from llm import build_llm
from langgraph_tools import CuentaCorrienteInput

# (pregunta, argumentos esperados que SÍ importan)
CASES = [
    ("¿Cuál es el saldo del proveedor 123456?",
     {"proveedor_id": "123456", "solo_abiertas": True, "incluir_partidas": False}),
    ("¿Cuánto tengo vencido con el acreedor 0000998877?",
     {"proveedor_id": "0000998877", "solo_vencidas": True}),
    ("Dame el detalle documento por documento del proveedor 45120",
     {"proveedor_id": "45120", "incluir_partidas": True}),
    ("Mostrame todas las partidas del 77001, incluidas las ya pagadas",
     {"proveedor_id": "77001", "solo_abiertas": False}),
    ("¿El acreedor 300500 tiene algo vencido sin pagar?",
     {"proveedor_id": "300500", "solo_abiertas": True, "solo_vencidas": True}),
    ("Necesito la antigüedad de deuda del proveedor 812345",
     {"proveedor_id": "812345", "incluir_partidas": False}),
    ("Traeme las primeras 10 partidas abiertas del 660022",
     {"proveedor_id": "660022", "incluir_partidas": True, "limit": 10}),
]

TOOL_SCHEMA = {
    "name": "consultar_cuenta_corriente_proveedor",
    "description": (
        "Devuelve saldos por moneda, aging por tramo de vencimiento y opcionalmente "
        "el detalle de partidas de la cuenta corriente de un proveedor."
    ),
    "input_schema": CuentaCorrienteInput.model_json_schema(),
}


def main() -> None:
    llm = build_llm().bind_tools([TOOL_SCHEMA], tool_choice="any")
    provider = os.getenv("LLM_PROVIDER", "anthropic")

    ok = 0
    for pregunta, esperado in CASES:
        resp = llm.invoke(pregunta)
        calls = getattr(resp, "tool_calls", [])
        if not calls:
            print(f"[SIN TOOL CALL] {pregunta}")
            continue

        args = calls[0]["args"]
        diffs = {
            k: (v, args.get(k))
            for k, v in esperado.items()
            if args.get(k) != v
        }
        if diffs:
            print(f"[FAIL] {pregunta}\n       esperado/obtenido: {json.dumps(diffs, ensure_ascii=False)}")
        else:
            ok += 1

    print(f"\n{provider}: {ok}/{len(CASES)} correctos")


if __name__ == "__main__":
    main()