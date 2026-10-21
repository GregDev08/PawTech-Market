"""Herramienta de búsqueda web para el investigador, usando browser_search de Groq.

La búsqueda se hace en una llamada aparte a Groq (fuera del bucle de CrewAI),
porque browser_search choca con el formato de prompt que usa CrewAI.
"""
import os
import re

from crewai.tools import tool
from openai import OpenAI

#SEARCH_MODEL = "openai/gpt-oss-120b" 
SEARCH_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b") 
 # browser_search solo funciona con los gpt-oss # browser_search solo funciona con los gpt-oss
MAX_CHARS = 3000                      # tope para no reventar el límite de tokens de Groq
_client = None


def _groq() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url="https://api.groq.com/openai/v1",
                         api_key=os.getenv("GROQ_API_KEY"))
    return _client


def groq_web_search(query: str) -> str:
    """Busca en la web con Groq y devuelve el texto de la respuesta más las URLs consultadas."""
    resp = _groq().chat.completions.create(
        model=SEARCH_MODEL,
        messages=[{
            "role": "user",
            "content": (f"Busca en la web: {query}\n"
                        "Responde en español con los datos concretos que encuentres "
                        "(marcas, productos, precios en euros) y la URL de cada dato."),
        }],
        tools=[{"type": "browser_search"}],
        tool_choice="required",   # obliga a buscar, no a contestar de memoria
        reasoning_effort="low",   # recomendado por Groq para no gastar tokens de más
        temperature=0.2,
    )
    msg = resp.choices[0].message
    text = re.sub(r"【[^】]*】", "", msg.content or "")  # quita las citas internas de Groq

    # Groq devuelve aparte las páginas que ha consultado: las añadimos para tener URLs reales
    executed = getattr(msg, "executed_tools", None) or []
    urls = []
    for t in executed:
        results = ((t.get("search_results") or {}).get("results") or []) if isinstance(t, dict) else []
        urls += [f"- {r.get('title', '')}: {r.get('url', '')}" for r in results]
    if urls:
        text += "\n\nPáginas consultadas:\n" + "\n".join(urls)
    return text[:MAX_CHARS]


@tool("Buscador web")
def web_search_tool(query: str) -> str:
    """Busca en internet información actual (marcas, productos, precios, tiendas) y devuelve
    los datos con sus URLs. Usa consultas concretas, p. ej. 'precio pienso Orijen adulto perro España'."""
    try:
        return groq_web_search(query)
    except Exception as exc:  # si una búsqueda falla, el agente puede probar otra consulta
        return f"La búsqueda falló ({exc}). Prueba con una consulta más simple."