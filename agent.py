"""Agente LangGraph sobre la cuenta corriente de proveedores.

    python agent.py                              # modo interactivo
    python agent.py "saldo del proveedor 123456" # una sola pregunta
"""
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langgraph.prebuilt import create_react_agent

from llm import build_llm
from langgraph_tools import TOOLS

load_dotenv()

SYSTEM = """Sos un asistente de Cuentas a Pagar sobre datos de SAP FI.

Reglas:
- Una partida está abierta cuando no tiene fecha de compensación.
- Los importes vienen en moneda documento y en moneda local; nunca los sumes
  entre monedas. Informá cada moneda por separado.
- Convención de signos: el SALDO NETO negativo es deuda con el proveedor. Las
  partidas individuales pueden ser positivas o negativas. Una partida positiva
  es un débito al acreedor (nota de crédito, anticipo o pago imputado), no una
  deuda adicional. Nunca describas una partida positiva como deuda.
- Pedí el detalle de partidas (incluir_partidas=True) solo si el usuario lo pide
  explícitamente. Para saldos, totales o antigüedad usá el agregado `aging` que
  ya devuelve la tool.
- El tramo 'sin_vencimiento' son partidas sin vencimiento neto cargado en SAP.
  No las cuentes como vencidas.
- Si la tool devuelve cantidad_partidas=0, el acreedor EXISTE pero no tiene
  partidas con esos filtros. Decilo así. No afirmes que el proveedor no existe.
- Si la tool devuelve {"error": "acreedor_inexistente"}, ese acreedor no está
  en la base. Decilo y no inventes datos.
- No inventes números que la tool no devolvió.
"""


def _build_agent():
    """El kwarg del system prompt cambió de nombre entre versiones de langgraph:
    messages_modifier -> state_modifier -> prompt. Se prueba en orden inverso
    para no atarse a una versión."""
    llm = build_llm()
    for kw in ("prompt", "state_modifier", "messages_modifier"):
        try:
            return create_react_agent(llm, TOOLS, **{kw: SYSTEM})
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
    raise RuntimeError(
        "Ninguna variante de system prompt fue aceptada. "
        "Actualizá langgraph: python -m pip install -U 'langgraph>=1.2,<2'"
    )


agent = _build_agent()

# Sonnet 5: USD por millón de tokens. Ajustar si cambiás de modelo.
PRECIO_IN, PRECIO_OUT = 2.0, 10.0


def preguntar(texto: str) -> None:
    tok_in = tok_out = 0

    # recursion_limit corta loops de tool-calling: sin esto un bug del agente
    # puede quemar el crédito reintentando la misma llamada.
    resultado = agent.invoke(
        {"messages": [("user", texto)]},
        config={"recursion_limit": 8},
    )

    for m in resultado["messages"]:
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", None) or []:
                print(f"  [tool] {tc['name']}({tc['args']})")
            u = getattr(m, "usage_metadata", None) or {}
            tok_in += u.get("input_tokens", 0)
            tok_out += u.get("output_tokens", 0)

    print(f"\n{resultado['messages'][-1].content}")
    costo = tok_in / 1e6 * PRECIO_IN + tok_out / 1e6 * PRECIO_OUT
    print(f"\n  [{tok_in} in / {tok_out} out -> USD {costo:.4f}]")


def main() -> None:
    if len(sys.argv) > 1:
        preguntar(" ".join(sys.argv[1:]))
        return

    print("Consultas sobre cuenta corriente de proveedores. Enter vacío para salir.\n")
    while True:
        try:
            texto = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            break
        preguntar(texto)
        print()


if __name__ == "__main__":
    main()