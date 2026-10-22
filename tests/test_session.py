"""Tests de graph/session.py: el puente entre el grafo y la interfaz.

Compruebo lo que verá la interfaz en cada momento ("data" con el formato de Josema
y "session" con la fase, los intentos y los resultados) y que las acciones fuera
de momento se rechazan, aunque la interfaz llegue a enviarlas.
"""
import time

import pytest

from graph.session import StudySession


def wait_until(session, phase, hito, timeout=30):
    """La sesión trabaja en otro hilo: espero a que llegue a la fase indicada."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = session.snapshot()["session"]
        if s["phase"] == "error":
            raise AssertionError(s["error"])
        if s["phase"] == phase and s["current_hito"] == hito and not session.busy:
            return session.snapshot()
        time.sleep(0.05)
    raise AssertionError(f"No llegó a {phase} del Hito {hito}: {session.snapshot()['session']['phase']}")


def test_las_subtareas_llegan_con_el_formato_de_la_interfaz(fake_llm):
    session = StudySession()
    session.start("pienso barato para gatos")
    view = wait_until(session, "awaiting_approval", 1)
    task = view["data"][1][0]
    assert {"id", "name", "progress", "status"} <= task.keys()   # lo que ya usaba app.py
    assert task["status"] == "waiting_approval" and task["name"].startswith("[Investigación Web]")


def test_recorrido_completo_desde_la_interfaz(fake_llm):
    session = StudySession()
    session.start("pienso barato para gatos")
    wait_until(session, "awaiting_approval", 1)

    session.approve_subtasks(1, ["H1-ST-01"])
    view = wait_until(session, "awaiting_review", 1)
    assert [t["status"] for t in view["data"][1]] == ["completed", "skipped", "skipped"]
    assert view["session"]["results"][1]["kind"] == "research"

    session.review_hito(1, "redo", "más marcas")
    view = wait_until(session, "awaiting_approval", 1)
    assert view["session"]["attempts"][1] == 2 and view["session"]["results"][1] is None

    session.approve_subtasks(1, ["H1-ST-01"])
    wait_until(session, "awaiting_review", 1)
    session.review_hito(1, "approve")
    wait_until(session, "awaiting_approval", 2)
    session.approve_subtasks(2, ["H2-ST-01"])
    wait_until(session, "awaiting_review", 2)
    session.review_hito(2, "approve")
    wait_until(session, "awaiting_approval", 3)
    session.approve_subtasks(3, ["H3-ST-01", "H3-ST-02"])
    wait_until(session, "awaiting_review", 3)
    session.review_hito(3, "approve")

    view = wait_until(session, "done", 3)
    assert "## Supervisión humana" in view["session"]["final"]["markdown"]


def test_acciones_fuera_de_momento_se_rechazan(fake_llm):
    session = StudySession()
    with pytest.raises(ValueError):
        session.start("   ")                                   # consulta vacía
    session.start("pienso barato para gatos")
    wait_until(session, "awaiting_approval", 1)
    with pytest.raises(ValueError):
        session.review_hito(1, "approve")                      # aún no hay resultado que revisar
    with pytest.raises(ValueError):
        session.approve_subtasks(1, [])                        # sin subtareas marcadas
    with pytest.raises(ValueError):
        session.approve_subtasks(2, ["H2-ST-01"])              # hito equivocado


def test_reset_deja_el_estudio_vacio(fake_llm):
    session = StudySession()
    session.start("pienso barato para gatos")
    wait_until(session, "awaiting_approval", 1)
    session.reset()
    view = session.snapshot()
    assert view["session"]["phase"] == "idle" and view["data"] == {1: [], 2: [], 3: []}
