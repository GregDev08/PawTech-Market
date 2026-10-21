"""Orquestación LangGraph de PawTech-Market en 3 hitos con Human-in-the-Loop.

Cada hito sigue el mismo ciclo:
    plan_hito → approve_subtasks (pausa) → execute_hito → review_hito (pausa)
    · rehacer          → vuelve a plan_hito del mismo hito
    · aprobar hito 1-2 → pasa al siguiente hito
    · aprobar hito 3   → finalize → fin
"""
import json
from pathlib import Path
from typing import Optional, TypedDict

import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.schemas import IntermediateValidation, MarketReportSchema, PlanProposal
from graph import runner
from graph.schemas import ResearchFindings

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
MAX_SUBTASKS = 6
MAX_ATTEMPTS = 3  # veces que se puede hacer cada hito (1 original + 2 "rehacer")

# Las instrucciones de cada tarea las escribió Vanesa en tasks.yaml: las reutilizamos
with open(ROOT / "agents" / "config" / "tasks.yaml", "r", encoding="utf-8") as _f:
    TASKS_CONFIG = yaml.safe_load(_f)

# Qué hace cada hito, qué agente lo planifica y qué tipos de subtarea admite
HITO_CONFIG = {
    1: {
        "title": "Planificación y Aprobación de Subtareas",
        "planner": "market_researcher",
        "categories": ["Investigación Web"],
    },
    2: {
        "title": "Validación Cuantitativa (MCP) y Visual",
        "planner": "data_analyst",
        "categories": ["Análisis Cuantitativo", "Análisis Visual"],
    },
    3: {
        "title": "Aprobación Final de Informe y Automatización",
        "planner": "strategic_writer",
        "categories": ["Redacción Estratégica", "Revisión Crítica"],
    },
}


class StudyState(TypedDict, total=False):
    """La "memoria" del grafo: todo lo que los nodos leen y escriben."""
    query: str                       # lo que pidió el usuario
    hito: int                        # en qué hito estamos (1, 2 o 3)
    attempts: dict[int, int]         # cuántas veces se ha intentado cada hito
    feedback: Optional[str]          # comentario del usuario al pedir "rehacer"
    proposals: dict[int, list[dict]] # subtareas propuestas en cada hito
    approved_ids: list[str]          # las que el usuario marcó en los checkboxes
    hito_results: dict[int, dict]    # lo que se le enseña al usuario al final de cada hito
    research: dict                   # ResearchFindings del Hito 1
    validation: dict                 # IntermediateValidation del Hito 2
    report: dict                     # MarketReportSchema del Hito 3
    decision: str                    # "approve", "redo" o "redo_blocked" en la última revisión
    final: dict                      # el informe exportado al terminar


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────
def _emit(event: dict) -> None:
    """Envía un evento en vivo a quien esté escuchando el grafo (la interfaz).

    Fuera del grafo (p. ej. probando un nodo suelto) no hay nadie escuchando: no hace nada.
    """
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(event)


def _truncate(text: str, limit: int = 3500) -> str:
    """Recorta textos largos para no gastar tokens de más en los prompts."""
    return text if len(text) <= limit else text[:limit] + "\n[…recortado…]"


def _match_category(raw: str, allowed: list[str]) -> Optional[str]:
    """Ajusta la categoría que escribe el LLM a una de las permitidas en el hito.

    El LLM a veces escribe 'investigación web' o 'Análisis de precios' en vez del
    nombre exacto: primero buscamos coincidencia exacta y luego por palabras clave.
    """
    value = (raw or "").strip().lower()
    for cat in allowed:
        if value == cat.lower():
            return cat
    keywords = {
        "Investigación Web": ("investig", "web", "tendenc", "competid", "búsqueda", "busqueda"),
        "Análisis Cuantitativo": ("cuantit", "numér", "numer", "precio", "estad", "dato"),
        "Análisis Visual": ("visual", "imagen", "packaging", "etiqueta", "gráfic", "grafic"),
        "Redacción Estratégica": ("redac", "informe", "síntesis", "sintesis", "estrateg"),
        "Revisión Crítica": ("revis", "auditor", "verific", "crític", "critic"),
    }
    for cat in allowed:
        if any(k in value for k in keywords[cat]):
            return cat
    return None  # categoría que no pertenece a este hito: se descarta


def _normalize_tasks(plan: PlanProposal, hito: int) -> list[dict]:
    """Convierte el PlanProposal del agente en la lista de subtareas que verá la interfaz."""
    allowed = HITO_CONFIG[hito]["categories"]
    tasks = []
    for sub in plan.proposed_tasks:
        category = _match_category(sub.category, allowed)
        if category is None:
            continue
        tasks.append({
            "id": f"H{hito}-ST-{len(tasks) + 1:02d}",   # IDs nuestros: H1-ST-01, H1-ST-02…
            "title": sub.title.strip(),
            "description": sub.description.strip(),
            "category": category,
            "agent": runner.CATEGORY_AGENT[category],  # quién la ejecutará
        })
        if len(tasks) >= MAX_SUBTASKS:
            break
    if not tasks:
        raise ValueError(
            f"El planificador no propuso subtareas válidas para el Hito {hito} "
            f"(categorías esperadas: {', '.join(allowed)})."
        )
    return tasks


def _context_for(state: StudyState, hito: int) -> str:
    """Lo que cada agente necesita saber de los hitos anteriores."""
    parts = [f"Solicitud del usuario: {state['query']}"]
    if hito >= 2 and state.get("research"):
        r = state["research"]
        parts.append("Hallazgos validados del Hito 1:\n" + _truncate(r["summary"], 2000))
        if r.get("competitors"):
            lines = []
            for c in r["competitors"]:
                price = f"{c['price_eur']} €" if c.get("price_eur") is not None else "precio s/d"
                size = f"{c['size_kg']} kg" if c.get("size_kg") else "tamaño s/d"
                per_kg = f"{c['price_per_kg']} €/kg" if c.get("price_per_kg") else "€/kg s/d"
                lines.append(f"- {c['name']} | {c['product']} | {price} | {size} | {per_kg} | "
                             f"{c.get('source') or 'sin fuente'}")
            parts.append("Competidores identificados:\n" + "\n".join(lines))
    if hito >= 3 and state.get("validation"):
        parts.append("Validación del Hito 2:\n"
                     + _truncate(json.dumps(state["validation"], ensure_ascii=False, indent=1), 3000))
    return "\n\n".join(parts)


def _feedback_block(state: StudyState) -> str:
    """Si el usuario pidió rehacer el hito, su comentario se añade al prompt."""
    fb = (state.get("feedback") or "").strip()
    return f"\n\nIMPORTANTE — el usuario pidió rehacer este hito con este comentario:\n{fb}" if fb else ""


# ──────────────────────────────────────────────────────────────────────────────
# Nodos: planificar y aprobar
# ──────────────────────────────────────────────────────────────────────────────
def plan_hito(state: StudyState) -> dict:
    """Un agente propone las subtareas del hito actual."""
    hito = state["hito"]
    cfg = HITO_CONFIG[hito]
    _emit({"event": "phase", "hito": hito, "phase": "planning",
           "message": f"El agente planificador está proponiendo subtareas para el Hito {hito}…"})

    categories = ", ".join(f"'{c}'" for c in cfg["categories"])
    base = TASKS_CONFIG["propose_research_plan"]["description"].strip() if hito == 1 else ""
    description = (
        f"{_context_for(state, hito)}\n\n"
        f"{base}\n\n"
        f"Estás planificando el HITO {hito}: {cfg['title']}.\n"
        f"Propón entre 2 y {MAX_SUBTASKS} subtareas concretas para este hito. "
        f"El campo 'category' de cada subtarea debe ser EXACTAMENTE una de: {categories}.\n"
        "Solo planifica: NO uses herramientas ni busques en la web todavía."
        f"{_feedback_block(state)}\n\n"
        "Responde en español."
    )
    result = runner.run_agent_task(
        cfg["planner"],
        description,
        "Un objeto PlanProposal con las subtareas del hito listas para aprobación humana.",
        output_pydantic=PlanProposal,
    )
    proposals = dict(state.get("proposals") or {})
    proposals[hito] = _normalize_tasks(result.pydantic, hito)
    return {"proposals": proposals}


def approve_subtasks(state: StudyState) -> dict:
    """PAUSA: el grafo se detiene hasta que el usuario marca los checkboxes."""
    hito = state["hito"]
    tasks = state["proposals"][hito]
    # interrupt() congela el grafo y entrega este dict a la interfaz.
    # Cuando el usuario responde, interrupt() devuelve su respuesta y seguimos aquí.
    answer = interrupt({"type": "approve_subtasks", "hito": hito, "tasks": tasks})
    valid_ids = {t["id"] for t in tasks}
    approved = [i for i in (answer or {}).get("approved_ids", []) if i in valid_ids]
    return {"approved_ids": approved}


def route_after_approval(state: StudyState) -> str:
    """Si no aprobó ninguna, volvemos a preguntar; si aprobó alguna, a ejecutar."""
    return "execute_hito" if state.get("approved_ids") else "approve_subtasks"


# ──────────────────────────────────────────────────────────────────────────────
# Ejecución de subtareas
# ──────────────────────────────────────────────────────────────────────────────
def _run_subtask(hito: int, task: dict, description: str, expected_output: str) -> dict:
    """Ejecuta UNA subtarea avisando a la interfaz de su progreso. Nunca lanza excepción:
    si falla, la subtarea queda marcada como 'failed' y el hito sigue con las demás."""
    progress = {"value": 10}
    _emit({"event": "task", "hito": hito, "task_id": task["id"], "status": "in_progress", "progress": 10})

    def on_step() -> None:
        # Cada paso del agente (una búsqueda, una respuesta…) avanza la barra un poco
        progress["value"] = min(90, progress["value"] + 15)
        _emit({"event": "task", "hito": hito, "task_id": task["id"],
               "status": "in_progress", "progress": progress["value"]})

    try:
        result = runner.run_agent_task(task["agent"], description, expected_output, on_step=on_step)
        output = result.raw.strip()
        _emit({"event": "task", "hito": hito, "task_id": task["id"], "status": "completed",
               "progress": 100, "output": output})
        return {**task, "status": "completed", "output": output}
    except Exception as exc:  # el fallo se muestra en la interfaz
        error = f"{exc.__class__.__name__}: {exc}"
        _emit({"event": "task", "hito": hito, "task_id": task["id"], "status": "failed",
               "progress": 100, "error": error})
        return {**task, "status": "failed", "error": error}


def _subtask_prompt(state: StudyState, hito: int, task: dict, base_task_key: str, extra: str = "") -> str:
    """Prompt de una subtarea: contexto + pautas de Vanesa + la subtarea aprobada."""
    base = TASKS_CONFIG[base_task_key]["description"].strip()
    return (
        f"{_context_for(state, hito)}\n\n"
        f"Pautas generales de tu rol:\n{base}\n\n"
        f"Subtarea aprobada por el usuario ({task['id']}): {task['title']}\n"
        f"{task['description']}"
        f"{extra}"
        f"{_feedback_block(state)}\n\n"
        "No inventes datos: si algo no se puede verificar, dilo explícitamente. "
        "Responde en español."
    )


def _store_result(state: StudyState, hito: int, result: dict) -> dict:
    """Guarda lo que verá el usuario al revisar el hito, sin borrar los de otros hitos."""
    results = dict(state.get("hito_results") or {})
    results[hito] = result
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Nodo: ejecutar el hito
# ──────────────────────────────────────────────────────────────────────────────
def execute_hito(state: StudyState) -> dict:
    hito = state["hito"]
    approved = [t for t in state["proposals"][hito] if t["id"] in state["approved_ids"]]
    _emit({"event": "phase", "hito": hito, "phase": "executing",
           "message": f"Los agentes están ejecutando {len(approved)} subtarea(s) del Hito {hito}…"})
    executors = {1: _execute_hito_1}  # los Hitos 2 y 3 se añaden en los siguientes pasos
    if hito not in executors:
        raise NotImplementedError(f"El Hito {hito} todavía no está implementado.")
    return executors[hito](state, approved)


def _execute_hito_1(state: StudyState, approved: list[dict]) -> dict:
    """Hito 1: cada subtarea investiga en la web y luego se consolida todo en ResearchFindings."""
    # 1) Una investigación por subtarea aprobada
    done = [
        _run_subtask(1, t, _subtask_prompt(
            state, 1, t, "propose_research_plan",
            "\n\nEjecuta ahora esta investigación usando el buscador web (como mucho 3 búsquedas). "
            "Incluye competidores, productos, precio en euros, tamaño del envase en kg "
            "y la URL de cada dato."),
            "Hallazgos de la investigación con competidores, precios, tamaños y fuentes.")
        for t in approved
    ]
    ok = [t for t in done if t["status"] == "completed"]
    if not ok:
        raise RuntimeError("Todas las subtareas del Hito 1 fallaron.")

    # 2) Consolidar las notas de todas las subtareas en un único ResearchFindings
    _emit({"event": "phase", "hito": 1, "phase": "executing",
           "message": "Consolidando hallazgos y extrayendo precios para el análisis cuantitativo…"})
    notes = "\n\n".join(f"### {t['id']} — {t['title']}\n{_truncate(t['output'], 2500)}" for t in ok)
    consolidated = runner.run_agent_task(
        "market_researcher",
        f"Solicitud del usuario: {state['query']}\n\nNotas de investigación:\n{notes}\n\n"
        "Consolida estas notas en un ResearchFindings. NO busques en la web: usa solo las notas. "
        "En 'competitors' incluye solo competidores mencionados en las notas; 'price_eur' y "
        "'size_kg' solo si aparecen en las notas (si no, null). No inventes precios ni fuentes."
        f"{_feedback_block(state)}\n\n"
        "Responde en español.",
        "Un objeto ResearchFindings.",
        output_pydantic=ResearchFindings,
    ).pydantic

    research = consolidated.model_dump()  # incluye price_per_kg calculado
    result = {
        "kind": "research",
        "summary": research["summary"],
        "competitors": research["competitors"],
        "sources": research["sources"],
        "comparable_prices": sum(1 for c in research["competitors"] if c.get("price_per_kg")),
        "subtasks": done,
    }
    return {"research": research, "hito_results": _store_result(state, 1, result)}


# ──────────────────────────────────────────────────────────────────────────────
# Nodos: revisar el hito y avanzar
# ──────────────────────────────────────────────────────────────────────────────
def review_hito(state: StudyState) -> dict:
    """PAUSA: el usuario ve el resultado del hito y decide aprobar o rehacer.

    El bucle de revisión tiene un máximo de MAX_ATTEMPTS intentos por hito.
    """
    hito = state["hito"]
    attempt = (state.get("attempts") or {}).get(hito, 1)
    answer = interrupt({
        "type": "review_hito",
        "hito": hito,
        "result": state["hito_results"][hito],
        "attempt": attempt,
        "max_attempts": MAX_ATTEMPTS,
        "can_redo": attempt < MAX_ATTEMPTS,  # la interfaz desactiva "rehacer" si es False
    })
    if (answer or {}).get("decision") == "redo":
        if attempt >= MAX_ATTEMPTS:
            # Límite alcanzado: no se rehace, se vuelve a preguntar (solo queda aprobar)
            return {"decision": "redo_blocked"}
        attempts = dict(state.get("attempts") or {})
        attempts[hito] = attempt + 1
        return {"decision": "redo", "feedback": (answer or {}).get("feedback", ""), "attempts": attempts}
    return {"decision": "approve", "feedback": None}


def route_after_review(state: StudyState) -> str:
    """Rehacer → volver a planificar. Rehacer bloqueado → volver a preguntar.
    Aprobar → siguiente hito o terminar."""
    decision = state.get("decision")
    if decision == "redo":
        return "plan_hito"
    if decision == "redo_blocked":
        return "review_hito"
    return "advance" if state["hito"] < 3 else "finalize"


def advance(state: StudyState) -> dict:
    """Pasa al siguiente hito y limpia la selección de checkboxes."""
    return {"hito": state["hito"] + 1, "approved_ids": []}


def finalize(state: StudyState) -> dict:
    """Fin del estudio. Se completará en el Hito 3 (exportar el informe)."""
    return {"final": {}}


# ──────────────────────────────────────────────────────────────────────────────
# Grafo
# ──────────────────────────────────────────────────────────────────────────────
def build_graph(checkpointer=None):
    builder = StateGraph(StudyState)

    # Las casillas
    builder.add_node("plan_hito", plan_hito)
    builder.add_node("approve_subtasks", approve_subtasks)
    builder.add_node("execute_hito", execute_hito)
    builder.add_node("review_hito", review_hito)
    builder.add_node("advance", advance)
    builder.add_node("finalize", finalize)

    # Las flechas fijas
    builder.add_edge(START, "plan_hito")
    builder.add_edge("plan_hito", "approve_subtasks")
    builder.add_edge("execute_hito", "review_hito")
    builder.add_edge("advance", "plan_hito")
    builder.add_edge("finalize", END)

    # Las flechas que dependen de lo que decida el usuario
    builder.add_conditional_edges("approve_subtasks", route_after_approval,
                                  ["execute_hito", "approve_subtasks"])
    builder.add_conditional_edges("review_hito", route_after_review,
                                  ["plan_hito", "review_hito", "advance", "finalize"])

    # El checkpointer guarda el estado en cada pausa: sin él, interrupt() no funciona
    return builder.compile(checkpointer=checkpointer or InMemorySaver())