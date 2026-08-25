"""Fábrica de modelo. El 'cerebro' es una variable de entorno, no una línea de código.

LLM_PROVIDER=anthropic|deepseek
"""
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()


def build_llm():
    if PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # Sin `temperature`: de la generación 4.6 en adelante los parámetros
        # de sampling fueron removidos y pasarlos devuelve error.
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            max_tokens=2000,
        )

    if PROVIDER == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        # deepseek-chat / deepseek-reasoner fueron retirados el 2026-07-24.
        # IDs vigentes: deepseek-v4-flash, deepseek-v4-pro.
        return ChatDeepSeek(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            temperature=0,
            max_tokens=2000,
        )

    raise ValueError(f"LLM_PROVIDER desconocido: {PROVIDER}")