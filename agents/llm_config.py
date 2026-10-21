import os

from crewai import LLM

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
TEXT_MODEL = "openai/gpt-oss-120b"
VISION_MODEL = "qwen/qwen3.8-27b"


def build_llm(kind: str = "text") -> LLM:
    """Devuelve el LLM de Groq. kind='vision' usa el modelo que entiende imágenes."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GROQ_API_KEY en el .env")

    if kind == "vision":
        model = os.getenv("VISION_LLM_MODEL", VISION_MODEL)
    else:
        model = os.getenv("LLM_MODEL", TEXT_MODEL)

    return LLM(
        model=f"openai/{model}",
        base_url=GROQ_BASE_URL,
        api_key=api_key,
        temperature=0.2,
    )