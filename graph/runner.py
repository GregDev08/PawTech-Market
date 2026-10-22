"""Ejecución de una tarea CrewAI con un solo agente.

Es el único punto donde la orquestación toca CrewAI.
Con FAKE_LLM=1 devuelve respuestas simuladas (graph/fake_llm.py) sin llamar a Groq.
"""
import json
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional, Type

from pydantic import BaseModel, ValidationError

from agents.llm_config import build_llm

# Qué agente ejecuta cada categoría de subtarea
CATEGORY_AGENT = {
    "Investigación Web": "market_researcher",
    "Análisis Cuantitativo": "data_analyst",
    "Análisis Visual": "visual_analyst",
    "Redacción Estratégica": "strategic_writer",
    "Revisión Crítica": "critical_reviewer",
}


@dataclass
class RunResult:
    raw: str                              # texto tal cual lo devolvió el agente
    pydantic: Optional[BaseModel] = None  # el mismo resultado validado, si pedimos esquema


def _create_agent(agent_key: str):
    from agents import crew_agents
    from graph.web_search import web_search_tool

    # Asignación de los tipos exactos que espera build_llm(): "light", "heavy" o "vision"
    if agent_key == "market_researcher":
        agent = crew_agents.get_market_researcher(tools=[web_search_tool])
        model_type = "light"  # Usa el modelo rápido de menor consumo
    elif agent_key == "data_analyst":
        agent = crew_agents.get_data_analyst()
        model_type = "light"
    elif agent_key == "visual_analyst":
        agent = crew_agents.get_visual_analyst()
        model_type = "vision" # Modelo multimodal para imágenes
    elif agent_key == "strategic_writer":
        agent = crew_agents.get_strategic_writer()
        model_type = "light"
    elif agent_key == "critical_reviewer":
        agent = crew_agents.get_critical_reviewer()
        model_type = "heavy"  # Modelo potente solo para auditar
    else:
        raise KeyError(f"Agente desconocido: {agent_key}")

    # Llamamos a build_llm pasando exactamente "light", "heavy" o "vision"
    agent.llm = build_llm(model_type)
    agent.allow_delegation = False
    agent.max_iter = 4  # Reducido para evitar bucles excesivos de tokens
    agent.verbose = os.getenv("AGENT_VERBOSE") == "1"
    return agent


def _parse_json_model(raw: str, model: Type[BaseModel]) -> BaseModel:
    """Busca el objeto JSON dentro del texto del agente y lo valida con Pydantic."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"La respuesta no contiene JSON para {model.__name__}.")
    try:
        return model.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"No se pudo validar {model.__name__}: {exc}") from exc


def _kickoff(agent_key: str, description: str, expected_output: str,
             on_step: Optional[Callable[[], None]]) -> str:
    """Monta una Crew mínima (1 agente, 1 tarea), la ejecuta y devuelve el texto."""
    from crewai import Crew, Process, Task

    agent = _create_agent(agent_key)
    crew = Crew(
        agents=[agent],
        tasks=[Task(description=description, expected_output=expected_output, agent=agent)],
        process=Process.sequential,
        verbose=agent.verbose,
        step_callback=(lambda _step: on_step()) if on_step else None,
    )
    return crew.kickoff().raw


def run_agent_task(
    agent_key: str,
    description: str,
    expected_output: str,
    output_pydantic: Optional[Type[BaseModel]] = None,
    on_step: Optional[Callable[[], None]] = None,
) -> RunResult:
    """Ejecuta una tarea con un agente. Si se pasa output_pydantic, exige ese JSON."""
    if os.getenv("FAKE_LLM") == "1":  # modo simulado: sin Groq, sin gastar tokens
        from graph.fake_llm import fake_result
        return fake_result(agent_key, description, output_pydantic, on_step)

    if output_pydantic is None:
        return RunResult(raw=_kickoff(agent_key, description, expected_output, on_step))

    # Pedimos el JSON en el propio prompt, adjuntando el esquema
    schema = json.dumps(output_pydantic.model_json_schema(), ensure_ascii=False)
    prompt = (f"{description}\n\nDevuelve ÚNICAMENTE un objeto JSON válido, sin texto adicional "
              f"ni bloques de código, que cumpla este JSON Schema:\n{schema}")
    expected = f"{expected_output} Solo el objeto JSON."

    raw = _kickoff(agent_key, prompt, expected, on_step)
    try:
        return RunResult(raw=raw, pydantic=_parse_json_model(raw, output_pydantic))
    except ValueError as exc:
        # Un reintento, diciéndole al agente qué falló
        retry_prompt = (f"{prompt}\n\nTu respuesta anterior no era válida ({exc}). "
                        "Corrígela y devuelve solo el JSON.")
        raw = _kickoff(agent_key, retry_prompt, expected, on_step)
        return RunResult(raw=raw, pydantic=_parse_json_model(raw, output_pydantic))