"""Respuestas simuladas de los agentes: prueban el grafo sin gastar tokens de Groq.

Se activa con FAKE_LLM=1 (en el .env o en la terminal). Útil para desarrollar la
interfaz, probar el bucle de revisión y hacer demos cuando se agota el cupo.
"""
import re
import time
from typing import Callable, Optional, Type

from pydantic import BaseModel

from agents.schemas import PlanProposal
from graph.schemas import ResearchFindings

DELAY = 0.4  # segundos por "paso" para que la interfaz tenga tiempo de mostrar el progreso

_PLANS = {
    1: [("Identificar las marcas principales", "Investigación Web"),
        ("Comparar precios por kg entre tiendas", "Investigación Web"),
        ("Revisar ofertas y suscripciones", "Investigación Web")],
    2: [("Estadísticas de precios €/kg", "Análisis Cuantitativo"),
        ("Analizar el packaging de las marcas", "Análisis Visual")],
    3: [("Redactar el informe final", "Redacción Estratégica"),
        ("Auditar el informe", "Revisión Crítica")],
}

# Datos de una ejecución real (pienso barato para gatos). Salvaje en saco aparece
# dos veces a propósito, para probar la eliminación de duplicados.
_COMPETITORS = [
    {"brand": "Start!", "product": "Adult Pollo y Buey", "store": "Tiendanimal",
     "price_eur": 4.99, "size_kg": 1,
     "source": "https://www.tiendanimal.es/start-adult-pollo-y-buey-pienso-para-gatos/KWK40948_M.html"},
    {"brand": "Salvaje", "product": "Adult Base Sterilised", "store": "Tiendanimal",
     "price_eur": 24.99, "size_kg": 12,
     "source": "https://www.tiendanimal.es/salvaje-adult-base-sterilised-pienso-para-gatos/SAB1244_M.html"},
    {"brand": "Salvaje", "product": "Adult Base Sterilised", "store": "Idealo",
     "price_eur": 25.49, "size_kg": 12,
     "source": "https://www.idealo.es/lista/121601890/pienso-salvaje-gatos.html"},
    {"brand": "Catxtreme", "product": "Sterilised Pollo y Buey", "store": "Carrefour",
     "price_eur": 4.99, "size_kg": 1, "source": "https://www.carrefour.es/"},
    {"brand": "Brit Care", "product": "Grain-Free Sterilised Adult", "store": "Zooplus",
     "price_eur": 37.99, "size_kg": 7,
     "source": "https://www.zooplus.es/shop/tienda_gatos/ofertas_especiales_gatos/pienso"},
]


def fake_result(agent_key: str, description: str,
                output_pydantic: Optional[Type[BaseModel]] = None,
                on_step: Optional[Callable[[], None]] = None):
    from graph.runner import RunResult  # import aquí para evitar un import circular

    for _ in range(3):  # simula 3 pasos del agente
        time.sleep(DELAY)
        if on_step:
            on_step()

    feedback = "IMPORTANTE" in description  # el prompt incluye el comentario de "rehacer"
    tag = " (rehecho con el comentario del usuario)" if feedback else ""

    if output_pydantic is PlanProposal:
        match = re.search(r"HITO (\d)", description)
        hito = int(match.group(1)) if match else 1
        tasks = [{"task_id": f"ST-0{i}", "title": title + tag,
                  "description": f"[simulado] {title}.", "category": cat}
                 for i, (title, cat) in enumerate(_PLANS[hito], 1)]
        plan = PlanProposal(proposed_tasks=tasks)
        return RunResult(raw=plan.model_dump_json(), pydantic=plan)

    if output_pydantic is ResearchFindings:
        findings = ResearchFindings.model_validate({
            "summary": f"[simulado] Cuatro marcas de pienso económico en tiendas españolas{tag}.",
            "competitors": _COMPETITORS,
            "sources": [c["source"] for c in _COMPETITORS],
        })
        return RunResult(raw=findings.model_dump_json(), pydantic=findings)

    if output_pydantic is not None:
        raise NotImplementedError(f"FAKE_LLM aún no simula {output_pydantic.__name__}.")

    return RunResult(raw=f"[simulado] Resultado de {agent_key}{tag}.")