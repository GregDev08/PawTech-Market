"""LLM de la squad: Groq a través de su endpoint compatible con OpenAI.

Variables del .env:
    GROQ_API_KEY=...                     (obligatoria)
    LLM_MODEL=openai/gpt-oss-120b        (opcional)
"""
import os

from crewai import LLM

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
TEXT_MODEL = "openai/gpt-oss-120b"
VISION_MODEL = "qwen/qwen3.8-27b"


def build_llm(kind: str = "text", web_search: bool = False) -> LLM:
    """Devuelve el LLM de Groq.

    kind='vision'   → modelo que entiende imágenes.
    web_search=True → activa browser_search, la búsqueda web nativa de Groq
                      (solo funciona con los modelos gpt-oss).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GROQ_API_KEY en el .env")

    if kind == "vision":
        model = os.getenv("VISION_LLM_MODEL", VISION_MODEL)
    else:
        model = os.getenv("LLM_MODEL", TEXT_MODEL)

    extra = {}
    if web_search:
        extra = {
            "tools": [{"type": "browser_search"}],
            "reasoning_effort": "low",  # Groq lo recomienda: si no, busca de más y gasta muchos tokens
        }

    return LLM(
        model=f"openai/{model}",
        base_url=GROQ_BASE_URL,
        api_key=api_key,
        temperature=0.2,
        additional_params=extra,
    )