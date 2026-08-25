"""Smoke test del RPC sin LLM. Aísla si un fallo es de Supabase o del modelo.
No consume crédito de la API de Claude.

    python test_rpc.py 123456
"""
import json
import sys

from langgraph_tools import consultar_cuenta_corriente_proveedor


def main() -> None:
    proveedor = sys.argv[1] if len(sys.argv) > 1 else "123456"

    casos = [
        ("saldo abierto", {"proveedor_id": proveedor}),
        ("solo vencidas", {"proveedor_id": proveedor, "solo_vencidas": True}),
        ("con detalle",   {"proveedor_id": proveedor, "incluir_partidas": True, "limit": 3}),
        ("inexistente",   {"proveedor_id": "0000000000"}),
    ]

    for nombre, args in casos:
        print(f"\n=== {nombre} ===")
        try:
            r = consultar_cuenta_corriente_proveedor.invoke(args)
            print(json.dumps(r, indent=2, ensure_ascii=False)[:1200])
        except Exception as exc:
            print(f"FALLO: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()