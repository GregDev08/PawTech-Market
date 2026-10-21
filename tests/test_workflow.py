"""Tests del grafo LangGraph: los 3 hitos, las pausas HITL y el bucle de revisión.

Aquí hago lo mismo que scripts/probar_hitos.py pero sin teclear: contesto a las
pausas con Command(resume=...) y compruebo que el grafo hace lo que debe.
Cubren mis tareas D6-7 (bucle con límite) y D8-10 (pausas Human-in-the-Loop).
"""
import json
import uuid

from langgraph.types import Command

from graph.workflow import MAX_ATTEMPTS, build_graph


class Flow:
    """Pequeño ayudante: ejecuta el grafo hasta la siguiente pausa y me la devuelve."""

    def __init__(self):
        self.graph = build_graph()
        self.config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    def run(self, graph_input):
        for _ in self.graph.stream(graph_input, self.config):
            pass
        state = self.graph.get_state(self.config)
        return state.interrupts[0].value if state.interrupts else None

    def start(self, query="pienso barato para gatos"):
        return self.run({"query": query, "hito": 1, "attempts": {1: 1, 2: 1, 3: 1}})

    def approve_tasks(self, ids):
        return self.run(Command(resume={"approved_ids": ids}))

    def review(self, decision, feedback=""):
        return self.run(Command(resume={"decision": decision, "feedback": feedback}))

    @property
    def values(self):
        return self.graph.get_state(self.config).values


def test_el_grafo_se_detiene_a_pedir_aprobacion_de_subtareas(fake_llm):
    pause = Flow().start()
    assert pause["type"] == "approve_subtasks" and pause["hito"] == 1
    assert all(t["category"] == "Investigación Web" for t in pause["tasks"])


def test_sin_subtareas_marcadas_vuelve_a_preguntar(fake_llm):
    flow = Flow()
    flow.start()
    pause = flow.approve_tasks([])
    assert pause["type"] == "approve_subtasks" and pause["hito"] == 1


def test_ids_falsos_se_ignoran(fake_llm):
    flow = Flow()
    flow.start()
    pause = flow.approve_tasks(["H1-ST-01", "INVENTADO"])
    assert pause["type"] == "review_hito"
    assert [t["id"] for t in pause["result"]["subtasks"]] == ["H1-ST-01"]


def test_hito_1_entrega_precios_comparables_sin_duplicados(fake_llm):
    flow = Flow()
    flow.start()
    result = flow.approve_tasks(["H1-ST-01"])["result"]
    assert result["kind"] == "research"
    assert result["duplicates_removed"] == 1           # el Salvaje repetido de fake_llm
    assert result["cheapest"]["brand"] == "Salvaje"    # calculado por código
    assert result["comparable_prices"] == 4


def test_rehacer_lleva_el_comentario_a_los_agentes(fake_llm):
    flow = Flow()
    flow.start()
    flow.approve_tasks(["H1-ST-01"])
    pause = flow.review("redo", "incluye marcas españolas")
    assert pause["type"] == "approve_subtasks"
    assert "rehecho con el comentario" in pause["tasks"][0]["title"]
    assert flow.values["attempts"][1] == 2


def test_bucle_de_revision_tiene_limite_de_intentos(fake_llm):
    flow = Flow()
    flow.start()
    pause = flow.approve_tasks(["H1-ST-01"])
    for attempt in range(1, MAX_ATTEMPTS):
        assert pause["attempt"] == attempt and pause["can_redo"]
        flow.review("redo", f"intento {attempt}")
        pause = flow.approve_tasks(["H1-ST-01"])
    assert pause["attempt"] == MAX_ATTEMPTS and not pause["can_redo"]

    # Rehacer con el límite alcanzado: se bloquea y vuelve a la misma revisión
    pause = flow.review("redo", "una más")
    assert pause["type"] == "review_hito" and pause["hito"] == 1 and pause["attempt"] == MAX_ATTEMPTS

    # Aprobar sigue funcionando: pasa al Hito 2
    pause = flow.review("approve")
    assert pause["type"] == "approve_subtasks" and pause["hito"] == 2


def test_flujo_completo_exporta_el_informe_con_supervision_humana(fake_llm):
    flow = Flow()
    flow.start()
    flow.approve_tasks(["H1-ST-01"])
    flow.review("redo", "más marcas")
    flow.approve_tasks(["H1-ST-01"])
    flow.review("approve")

    pause = flow.approve_tasks(["H2-ST-01", "H2-ST-02"])          # Hito 2
    stats = pause["result"]["quantitative_summary"]["estadisticas"]
    assert stats["row_count"] == 4 and round(stats["summary"]["precio_eur_kg"]["mean"], 2) == 4.37
    flow.review("approve")

    pause = flow.approve_tasks(["H3-ST-01", "H3-ST-02"])          # Hito 3
    report = pause["result"]["report"]
    assert "4,37 €/kg" in report["price_distribution_summary"]   # la cifra la puso el código
    assert pause["result"]["audit_verdict"] == "APROBADO"
    assert flow.review("approve") is None                         # sin más pausas: terminado

    final = flow.values["final"]
    md_path, json_path = final["files"]
    markdown = open(md_path, encoding="utf-8").read()
    assert "## Supervisión humana" in markdown and "pidió rehacer — «más marcas»" in markdown

    exported = json.load(open(json_path, encoding="utf-8"))
    decisions = exported["human_decisions"]
    assert len(decisions) == 8  # 4 en el Hito 1 (con el rehacer) + 2 + 2
    assert decisions[1] == {**decisions[1], "hito": 1, "decision": "redo", "feedback": "más marcas"}
