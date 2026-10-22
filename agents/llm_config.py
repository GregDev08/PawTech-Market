"""LLM de la squad: Groq a través de su endpoint compatible con OpenAI.

Variables del .env (ver .env.example):
    GROQ_API_KEY=...                        obligatoria
    LLM_MODEL=openai/gpt-oss-120b           opcional (también openai/gpt-oss-20b o qwen/qwen3.8-27b)
    VISION_LLM_MODEL=qwen/qwen3.8-27b       opcional, para el analista visual

Los agentes de agents/crew_agents.py se crean con su LLM por defecto y graph/runner.py
les asigna este, así no hace falta tocar el archivo de los agentes.
"""
import os

from crewai import LLM

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
LIGHT_MODEL = "gpt-oss-20b"
HEAVY_MODEL = "gpt-oss-120b"
VISION_MODEL = "qwen/qwen3.8-27b"


def build_llm(kind: str = "text") -> LLM:
    """Devuelve el LLM de Groq. kind='vision' usa el modelo que entiende imágenes."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GROQ_API_KEY en el .env")

    if kind == "vision":
        model = os.getenv("VISION_LLM_MODEL", VISION_MODEL)
    elif kind == "heavy":
        model = os.getenv("HEAVY_LLM_MODEL", HEAVY_MODEL)
    else:
        model = os.getenv("LLM_MODEL", LIGHT_MODEL)

    extra = {}
    if model.startswith("qwen/"):
        # Qwen "piensa en voz alta" por defecto: lo ocultamos para que no rompa el JSON
        extra["extra_body"] = {"reasoning_format": "hidden"}

    return LLM(
        model=f"openai/{model}",
        base_url=GROQ_BASE_URL,
        api_key=api_key,
        temperature=0.2,
        additional_params=extra,
    )