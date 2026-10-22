"""Orquestación LangGraph de PawTech-Market en 3 hitos con Human-in-the-Loop.

Cada hito sigue el mismo ciclo:
    plan_hito → approve_subtasks (pausa) → execute_hito → review_hito (pausa)
    · rehacer          → vuelve a plan_hito del mismo hito
    · aprobar hito 1-2 → pasa al siguiente hito
    · aprobar hito 3   → finalize → fin
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, TypedDict

import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.schemas import IntermediateValidation, MarketReportSchema, PlanProposal
from graph import mcp_client, runner
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
    human_log: list[dict]            # rastro de cada decisión humana (qué, en qué hito, cuándo)
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
                lines.append(f"- {c['brand']} | {c['product']} | {c.get('store') or 'tienda s/d'} | "
                             f"{price} | {size} | {per_kg} | {c.get('source') or 'sin fuente'}")
            parts.append("Competidores identificados:\n" + "\n".join(lines))
    if hito >= 3 and state.get("validation"):
        parts.append("Validación del Hito 2:\n"
                     + _truncate(json.dumps(state["validation"], ensure_ascii=False, indent=1), 3000))
    return "\n\n".join(parts)


def _log_decision(state: StudyState, entry: dict) -> list[dict]:
    """Apunto una decisión humana en el registro de supervisión.

    En un sistema Human-in-the-Loop no basta con que haya pausas: quiero poder
    demostrar qué decidió la persona en cada momento. Devuelvo la lista entera
    porque en LangGraph un nodo devuelve el valor nuevo del campo, no un "añade".
    """
    attempt = (state.get("attempts") or {}).get(state["hito"], 1)
    record = {"hito": state["hito"], "attempt": attempt, **entry,
              "at": datetime.now().isoformat(timespec="seconds")}
    return [*(state.get("human_log") or []), record]


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
    # Apunto lo que se aprobó y lo que se descartó (con título, que es lo que entiende una persona)
    log = _log_decision(state, {
        "action": "approve_subtasks",
        "approved": [t["title"] for t in tasks if t["id"] in approved],
        "rejected": [t["title"] for t in tasks if t["id"] not in approved],
    })
    return {"approved_ids": approved, "human_log": log}


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


def _dedupe_competitors(competitors: list[dict]) -> list[dict]:
    """Quita productos repetidos (misma marca, producto y tamaño en varias tiendas).

    Se queda con la oferta más barata en €/kg, para que un producto no cuente
    dos veces en las estadísticas del Hito 2.
    """
    best: dict[tuple, dict] = {}
    for c in competitors:
        key = (c["brand"].strip().lower(), c["product"].strip().lower(), c.get("size_kg"))
        current = best.get(key)
        if current is None or (c.get("price_per_kg") or float("inf")) < (current.get("price_per_kg") or float("inf")):
            best[key] = c
    return list(best.values())


def _cheapest(competitors: list[dict]) -> Optional[dict]:
    """El producto más barato en €/kg, calculado por nosotros (no por el LLM)."""
    priced = [c for c in competitors if c.get("price_per_kg")]
    return min(priced, key=lambda c: c["price_per_kg"]) if priced else None


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
    executors = {1: _execute_hito_1, 2: _execute_hito_2, 3: _execute_hito_3}
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
        "En 'competitors' incluye una entrada por producto mencionado en las notas: en 'brand' la "
        "MARCA del producto y en 'store' la tienda donde se vio. 'price_eur' y 'size_kg' solo si "
        "aparecen en las notas (si no, null). No inventes precios ni fuentes. En 'summary' no "
        "escribas cálculos de €/kg ni rankings de precio: los calculamos aparte."
        f"{_feedback_block(state)}\n\n"
        "Responde en español.",
        "Un objeto ResearchFindings.",
        output_pydantic=ResearchFindings,
    ).pydantic

    research = consolidated.model_dump()  # incluye price_per_kg calculado
    found = len(research["competitors"])
    research["competitors"] = _dedupe_competitors(research["competitors"])
    result = {
        "kind": "research",
        "summary": research["summary"],
        "competitors": research["competitors"],
        "sources": research["sources"],
        "comparable_prices": sum(1 for c in research["competitors"] if c.get("price_per_kg")),
        "duplicates_removed": found - len(research["competitors"]),
        "cheapest": _cheapest(research["competitors"]),
        "subtasks": done,
    }
    return {"research": research, "hito_results": _store_result(state, 1, result)}


# ──────────────────────────────────────────────────────────────────────────────
# Hito 2: validación cuantitativa (MCP) y visual
# ──────────────────────────────────────────────────────────────────────────────
def _price_rows(state: StudyState) -> list[dict[str, float]]:
    """Preparo las filas para la herramienta de Luis a partir de lo aprobado en el Hito 1.

    Uso el €/kg (no el precio total) porque es lo único comparable entre sacos de
    distinto tamaño. Su herramienta exige que todas las filas tengan las mismas
    columnas y números finitos, así que solo meto los productos que tienen €/kg.
    """
    competitors = (state.get("research") or {}).get("competitors", [])
    return [{"precio_eur_kg": float(c["price_per_kg"])} for c in competitors if c.get("price_per_kg")]


def _execute_hito_2(state: StudyState, approved: list[dict]) -> dict:
    """Hito 2: las cifras las calcula la herramienta MCP; los agentes solo las interpretan."""
    rows = _price_rows(state)
    wants_quant = any(t["category"] == "Análisis Cuantitativo" for t in approved)

    # 1) Estadísticas con la herramienta de Luis. Las calculo UNA vez, antes de los agentes,
    #    para que todos trabajen con las mismas cifras y ninguno se invente una media.
    if wants_quant and rows:
        _emit({"event": "phase", "hito": 2, "phase": "executing",
               "message": f"Calculando estadísticas de {len(rows)} precios €/kg con la herramienta MCP…"})
        stats = mcp_client.analyze_numeric_data(rows)
    elif wants_quant:
        stats = {"aviso": "El Hito 1 no aportó precios por kg: no hay datos que analizar."}
    else:
        stats = {"aviso": "No se aprobó ninguna subtarea cuantitativa."}

    # 2) Cada subtarea aprobada va a su agente, con el contexto que necesita
    done = []
    for t in approved:
        if t["category"] == "Análisis Cuantitativo":
            # Le paso las estadísticas ya calculadas y le prohíbo calcular otras
            extra = ("\n\nEstadísticas de €/kg calculadas por la herramienta MCP (son la ÚNICA "
                     f"fuente válida de cifras, no calcules otras):\n{json.dumps(stats, ensure_ascii=False)}"
                     "\n\nInterprétalas para esta subtarea: qué marcas quedan por encima o por "
                     "debajo de la media, cuánta dispersión hay y si se ven huecos de precio.")
            done.append(_run_subtask(2, t, _subtask_prompt(state, 2, t, "execute_data_analysis", extra),
                                     "Interpretación cuantitativa basada solo en las estadísticas dadas."))
        else:
            # Todavía no adjuntamos imágenes: el visual trabaja con lo que se sabe del producto
            extra = ("\n\nNo se han adjuntado imágenes: basa el análisis en los nombres de producto y "
                     "lo que dicen los hallazgos (claims como 'grain-free' o 'sterilised', formatos, "
                     "posicionamiento) y señala qué habría que comprobar viendo el packaging real.")
            done.append(_run_subtask(2, t, _subtask_prompt(state, 2, t, "execute_visual_analysis", extra),
                                     "Hallazgos visuales y de packaging."))

    if not any(t["status"] == "completed" for t in done):
        raise RuntimeError("Todas las subtareas del Hito 2 fallaron.")

    # 3) Junto todo en el esquema de Vanesa para la pausa de validación
    quant_text = "\n\n".join(t["output"] for t in done
                             if t["category"] == "Análisis Cuantitativo" and t["status"] == "completed")
    visual_text = "\n\n".join(t["output"] for t in done
                              if t["category"] == "Análisis Visual" and t["status"] == "completed")
    validation = IntermediateValidation(
        quantitative_summary={"estadisticas": stats, "interpretacion": quant_text or None},
        visual_findings=visual_text or "No se aprobaron (o fallaron) las subtareas de análisis visual.",
        sources_found=(state.get("research") or {}).get("sources", []),
    ).model_dump()

    result = {"kind": "validation", **validation, "price_rows": len(rows), "subtasks": done}
    return {"validation": validation, "hito_results": _store_result(state, 2, result)}


# ──────────────────────────────────────────────────────────────────────────────
# Hito 3: informe final y auditoría
# ──────────────────────────────────────────────────────────────────────────────
def _eur(value: float) -> str:
    """Escribo los números a la española (2,08 y no 2.08), que el informe es para personas."""
    return f"{value:.2f}".replace(".", ",")


def _price_summary(state: StudyState) -> str:
    """El párrafo de precios del informe lo escribo yo, con las cifras de MCP del Hito 2.

    Es la regla de todo el proyecto: las cifras salen del código, no del LLM. Así el
    revisor crítico (que según las pautas de Vanesa verifica que cada número venga del
    código) tiene una fuente clara, y nos ahorramos errores como el de los 1,43 €/kg.
    """
    stats = ((state.get("validation") or {}).get("quantitative_summary") or {}).get("estadisticas") or {}
    s = (stats.get("summary") or {}).get("precio_eur_kg")
    if not s:
        return "No hubo suficientes precios por kg para un resumen cuantitativo."
    text = (f"Se analizaron {int(s['count'])} productos. Precio medio {_eur(s['mean'])} €/kg "
            f"(mediana {_eur(s['50%'])} €/kg), con un rango de {_eur(s['min'])} a {_eur(s['max'])} €/kg")
    if s.get("std") is not None:
        text += f" y una desviación de {_eur(s['std'])} €/kg"
    text += "."
    cheapest = _cheapest((state.get("research") or {}).get("competitors", []))
    if cheapest:
        text += (f" El más económico es {cheapest['brand']} {cheapest['product']}"
                 f" ({cheapest.get('store') or 'tienda s/d'}) a {_eur(cheapest['price_per_kg'])} €/kg.")
    return text + f" Estadísticas calculadas vía {stats.get('via', 's/d')}."


def _audit_verdict(audits: list[str]) -> str:
    """Leo el veredicto que pido al revisor al final de su auditoría."""
    if not audits:
        return "SIN AUDITORÍA"
    text = " ".join(audits).upper()
    if "REQUIERE CAMBIOS" in text:
        return "REQUIERE CAMBIOS"
    return "APROBADO" if "APROBADO" in text else "SIN VEREDICTO"


def _execute_hito_3(state: StudyState, approved: list[dict]) -> dict:
    """Hito 3: borradores → informe consolidado (MarketReportSchema) → auditoría crítica."""
    writers = [t for t in approved if t["category"] == "Redacción Estratégica"]
    reviewers = [t for t in approved if t["category"] == "Revisión Crítica"]

    # 1) Cada subtarea de redacción escribe un borrador de su parte del informe
    done = [_run_subtask(3, t, _subtask_prompt(state, 3, t, "draft_final_report"),
                         "Borrador de la sección del informe.") for t in writers]
    drafts = "\n\n".join(f"### {t['title']}\n{_truncate(t['output'], 2500)}"
                         for t in done if t["status"] == "completed")

    # 2) El redactor consolida todo en el esquema de Vanesa. Le digo que deje en blanco
    #    la parte de precios: esa la relleno yo con las cifras de MCP.
    _emit({"event": "phase", "hito": 3, "phase": "executing",
           "message": "El redactor estratégico está consolidando el informe final…"})
    report = runner.run_agent_task(
        "strategic_writer",
        f"{_context_for(state, 3)}\n\n"
        f"{TASKS_CONFIG['draft_final_report']['description'].strip()}\n\n"
        f"Borradores aprobados:\n{drafts or '(no hay borradores: redacta a partir del contexto)'}\n\n"
        "En 'price_distribution_summary' escribe solo 'pendiente': lo rellenamos con las "
        "estadísticas calculadas. No escribas cifras de precio que no estén en el contexto."
        f"{_feedback_block(state)}\n\n"
        "Responde en español.",
        "Un objeto MarketReportSchema completo.",
        output_pydantic=MarketReportSchema,
    ).pydantic.model_dump()

    # Sustituyo lo que debe salir del código: el resumen de precios y las fuentes reales
    report["price_distribution_summary"] = _price_summary(state)
    report["sources"] = (state.get("research") or {}).get("sources", []) or report["sources"]

    # 3) El revisor crítico audita el informe ya consolidado y da un veredicto
    for t in reviewers:
        done.append(_run_subtask(3, t, _subtask_prompt(
            state, 3, t, "review_and_audit_report",
            f"\n\nInforme a auditar:\n{json.dumps(report, ensure_ascii=False, indent=1)}\n\n"
            "Comprueba que cada cifra coincide con las estadísticas del Hito 2 y que las fuentes "
            "están citadas. Termina con una línea 'Veredicto: APROBADO' o 'Veredicto: REQUIERE "
            "CAMBIOS', seguida de la lista de problemas si los hay."),
            "Auditoría del informe con veredicto final."))

    audits = [t["output"] for t in done if t["category"] == "Revisión Crítica" and t["status"] == "completed"]
    result = {"kind": "report", "report": report, "audit": audits,
              "audit_verdict": _audit_verdict(audits), "subtasks": done}
    return {"report": report, "hito_results": _store_result(state, 3, result)}


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
        feedback = (answer or {}).get("feedback", "")
        if attempt >= MAX_ATTEMPTS:
            # Límite alcanzado: no se rehace, se vuelve a preguntar (solo queda aprobar)
            log = _log_decision(state, {"action": "review", "decision": "redo_blocked", "feedback": feedback})
            return {"decision": "redo_blocked", "human_log": log}
        log = _log_decision(state, {"action": "review", "decision": "redo", "feedback": feedback})
        attempts = dict(state.get("attempts") or {})
        attempts[hito] = attempt + 1
        return {"decision": "redo", "feedback": feedback, "attempts": attempts, "human_log": log}
    log = _log_decision(state, {"action": "review", "decision": "approve"})
    return {"decision": "approve", "feedback": None, "human_log": log}


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


def _human_log_lines(log: list[dict]) -> list[str]:
    """Traduzco el registro de decisiones a frases que se entiendan en el informe."""
    lines = []
    for e in log:
        when = e["at"][11:16]  # solo la hora: HH:MM
        prefix = f"- {when} · Hito {e['hito']} (intento {e['attempt']}):"
        if e["action"] == "approve_subtasks":
            text = f"aprobó {len(e['approved'])} subtarea(s): {', '.join(e['approved'])}"
            if e["rejected"]:
                text += f" · descartó {len(e['rejected'])}"
        elif e["decision"] == "approve":
            text = "aprobó el resultado"
        elif e["decision"] == "redo":
            text = f"pidió rehacer — «{e['feedback']}»" if e.get("feedback") else "pidió rehacer"
        else:
            text = "intentó rehacer con el límite alcanzado (bloqueado)"
        lines.append(f"{prefix} {text}")
    return lines


def report_to_markdown(report: dict, audits: list[str], query: str, when: datetime,
                       human_log: list[dict] | None = None) -> str:
    """Convierto el informe a Markdown para que se pueda leer, compartir o pasar a PDF."""
    md = [f"# {report['title']}", "",
          f"*Estudio: {query} · Fecha: {when.strftime('%d/%m/%Y')} · Generado por PawTech-Market*", "",
          "## Resumen ejecutivo", report["executive_summary"], "",
          "## Análisis de competidores", report["competitor_analysis"], "",
          "## Distribución de precios", report["price_distribution_summary"], "",
          "## Insights visuales", report["visual_insights"], "",
          "## Recomendaciones"]
    md += [f"- {r}" for r in report["recommendations"]]
    md += ["", "## Fuentes"] + [f"- {s}" for s in report["sources"]]
    if audits:
        md += ["", "## Auditoría del revisor crítico"] + audits
    if human_log:
        md += ["", "## Supervisión humana",
               "Decisiones tomadas por la persona usuaria en cada pausa del flujo:", ""]
        md += _human_log_lines(human_log)
    return "\n".join(md) + "\n"


def finalize(state: StudyState) -> dict:
    """La "automatización" que el usuario autoriza al aprobar el Hito 3: exportar el informe.

    La fecha la pongo yo con datetime.now(): el LLM no sabe en qué día estamos
    (en una prueba puso "abril 2024" a precios de octubre de 2026).
    """
    _emit({"event": "phase", "hito": 3, "phase": "finalizing",
           "message": "Exportando el informe aprobado a outputs/…"})
    now = datetime.now()
    audits = state["hito_results"][3].get("audit", [])
    human_log = state.get("human_log") or []
    markdown = report_to_markdown(state["report"], audits, state["query"], now, human_log)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    md_path = OUTPUT_DIR / f"informe_{stamp}.md"
    json_path = OUTPUT_DIR / f"informe_{stamp}.json"
    md_path.write_text(markdown, encoding="utf-8")
    # El JSON guarda el estudio completo (los 3 hitos) por si alguien quiere revisar de dónde sale cada dato
    json_path.write_text(json.dumps({
        "query": state["query"], "date": now.isoformat(timespec="seconds"),
        "report": state["report"], "validation": state.get("validation"),
        "research": state.get("research"), "audit": audits,
        "human_decisions": human_log,  # quién decidió qué y cuándo: la prueba del Human-in-the-Loop
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"final": {"markdown": markdown, "files": [str(md_path), str(json_path)]}}


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