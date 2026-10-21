"""Puente entre mi grafo LangGraph y la interfaz de Josema.

El problema que resuelvo aquí: la interfaz (Streamlit + WebSocket) necesita ver el
estado del estudio en cada momento, pero el grafo tarda (los agentes llaman a Groq,
buscan en la web…) y además se detiene en las pausas Human-in-the-Loop.

La solución:
  · El grafo corre en un hilo aparte, para no bloquear el servidor.
  · Escucho sus eventos en vivo (_emit) y sus pausas (interrupt).
  · Con todo eso mantengo `view`: una "foto" del estudio en JSON que el servidor
    envía a la interfaz cada vez que cambia algo (on_change).

Fases del estudio (view["session"]["phase"]):
  idle → planning → awaiting_approval → executing → awaiting_review → … → done
  y "error" en cualquier punto (se puede reintentar con retry()).
"""
import copy
import threading
import uuid
from typing import Any, Callable, Optional

from langgraph.types import Command

from graph.workflow import HITO_CONFIG, MAX_ATTEMPTS, build_graph


def _empty_view() -> dict:
    """La foto de un estudio vacío.

    "data" tiene EXACTAMENTE el formato que ya usaba Josema ({hito: [subtareas]}),
    para que sus checkboxes y barras sigan funcionando. Todo lo nuevo va en "session".
    """
    return {
        "data": {1: [], 2: [], 3: []},
        "session": {
            "query": "",
            "phase": "idle",
            "current_hito": 1,
            "message": "",
            "error": None,
            "titles": {n: HITO_CONFIG[n]["title"] for n in (1, 2, 3)},
            "attempts": {1: 1, 2: 1, 3: 1},
            "max_attempts": MAX_ATTEMPTS,
            "can_redo": True,
            "results": {1: None, 2: None, 3: None},  # resultado real de cada hito
            "final": None,                           # informe exportado al terminar
        },
    }


def _task_for_ui(task: dict) -> dict:
    """Convierto una subtarea del grafo al formato de Josema (id, name, progress, status)
    y le añado lo que la interfaz puede querer enseñar después (salida, error…)."""
    return {
        "id": task["id"],
        "name": f"[{task['category']}] {task['title']} — {task['description']}",
        "progress": 0,
        "status": "waiting_approval",
        "category": task["category"],
        "agent": task["agent"],
        "output": None,
        "error": None,
    }


class SessionBusyError(RuntimeError):
    """Se lanza si llega una acción mientras los agentes todavía están trabajando."""


class StudySession:
    """Un estudio de mercado en marcha. El servidor tiene una y le pasa las acciones."""

    def __init__(self, on_change: Optional[Callable[[dict], None]] = None, graph=None):
        self.graph = graph or build_graph()
        self.on_change = on_change or (lambda _view: None)
        self.view = _empty_view()
        self.thread_id: Optional[str] = None
        self._lock = threading.RLock()           # el hilo del grafo y el servidor tocan la misma foto
        self._worker: Optional[threading.Thread] = None

    # ── Lo que llama el servidor ──────────────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.view)

    @property
    def busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def start(self, query: str) -> None:
        """SUBMIT_QUERY: arranco un estudio nuevo con un hilo (thread_id) nuevo."""
        query = (query or "").strip()
        if not query:
            raise ValueError("La consulta no puede estar vacía.")
        self._ensure_idle()
        with self._lock:
            self.thread_id = str(uuid.uuid4())
            self.view = _empty_view()
            self.view["session"]["query"] = query
        self._launch({"query": query, "hito": 1, "attempts": {1: 1, 2: 1, 3: 1}})

    def approve_subtasks(self, hito: int, approved_ids: list[str]) -> None:
        """START_TASKS: contesto a la pausa de los checkboxes."""
        self._require_phase("awaiting_approval", hito)
        if not approved_ids:
            raise ValueError("Selecciona al menos una subtarea.")
        with self._lock:
            for task in self.view["data"][hito]:
                approved = task["id"] in approved_ids
                task["status"] = "pending" if approved else "skipped"
                task["progress"] = 0
        self._launch(Command(resume={"approved_ids": list(approved_ids)}))

    def review_hito(self, hito: int, decision: str, feedback: str = "") -> None:
        """REVIEW_HITO: contesto a la pausa de revisión (aprobar o rehacer)."""
        self._require_phase("awaiting_review", hito)
        if decision not in ("approve", "redo"):
            raise ValueError("La decisión debe ser 'approve' o 'redo'.")
        if decision == "redo" and not self.view["session"]["can_redo"]:
            raise ValueError(f"Límite de {MAX_ATTEMPTS} intentos alcanzado: solo se puede aprobar.")
        with self._lock:
            s = self.view["session"]
            if decision == "redo":
                # Se vuelve a planificar este hito: limpio sus subtareas y su resultado
                self.view["data"][hito] = []
                s["results"][hito] = None
                s["attempts"][hito] += 1
            elif hito < 3:
                s["current_hito"] = hito + 1
        self._launch(Command(resume={"decision": decision, "feedback": feedback}))

    def retry(self) -> None:
        """RETRY: tras un error (p. ej. límite de Groq) reanudo desde el último punto guardado."""
        if self.view["session"]["phase"] != "error" or not self.thread_id:
            raise ValueError("Solo se puede reintentar tras un error.")
        self._launch(None)

    def reset(self) -> None:
        """RESET: vuelvo a un estudio vacío."""
        self._ensure_idle()
        with self._lock:
            self.thread_id = None
            self.view = _empty_view()
        self._notify()

    # ── Interno ───────────────────────────────────────────────────────────────
    def _ensure_idle(self) -> None:
        if self.busy:
            raise SessionBusyError("Los agentes están trabajando; espera a que terminen.")

    def _require_phase(self, phase: str, hito: int) -> None:
        """Compruebo que la acción tiene sentido ahora (no me fío de los botones)."""
        self._ensure_idle()
        s = self.view["session"]
        if s["phase"] != phase or s["current_hito"] != hito:
            raise ValueError(f"Acción no válida: el estudio está en '{s['phase']}' del Hito {s['current_hito']}.")

    def _set(self, **fields: Any) -> None:
        with self._lock:
            self.view["session"].update(fields)
        self._notify()

    def _notify(self) -> None:
        self.on_change(self.snapshot())

    def _launch(self, graph_input: Any) -> None:
        """Ejecuto el grafo en un hilo aparte para no bloquear el servidor."""
        with self._lock:
            self.view["session"]["error"] = None
        self._worker = threading.Thread(target=self._run, args=(graph_input,), daemon=True)
        self._worker.start()

    def _run(self, graph_input: Any) -> None:
        config = {"configurable": {"thread_id": self.thread_id}}
        self._set(phase="executing" if isinstance(graph_input, Command) else "planning")
        try:
            # "custom" = los eventos de _emit; los recibo mientras el grafo trabaja
            for mode, chunk in self.graph.stream(graph_input, config, stream_mode=["custom", "updates"]):
                if mode == "custom":
                    self._handle_event(chunk)
            self._sync_after_stop(config)  # el grafo se ha parado: ¿pausa o final?
        except Exception as exc:  # el error se enseña en la interfaz, con opción de reintentar
            with self._lock:
                s = self.view["session"]
                s["phase"] = "error"
                s["error"] = f"{exc.__class__.__name__}: {exc}"
                s["message"] = f"Error en el Hito {s['current_hito']}. Puedes reintentar."
            self._notify()

    def _handle_event(self, event: dict) -> None:
        """Traduzco los eventos del grafo (_emit) a cambios en la foto."""
        with self._lock:
            s = self.view["session"]
            if event["event"] == "phase":
                s["current_hito"] = event["hito"]
                s["phase"] = event["phase"]
                s["message"] = event.get("message", "")
            elif event["event"] == "task":
                for task in self.view["data"][event["hito"]]:
                    if task["id"] == event["task_id"]:
                        task["status"] = event["status"]
                        task["progress"] = event["progress"]
                        task["output"] = event.get("output", task["output"])
                        task["error"] = event.get("error", task["error"])
        self._notify()

    def _sync_after_stop(self, config: dict) -> None:
        """Cuando el grafo se para, miro por qué: una pausa HITL o el final del estudio."""
        state = self.graph.get_state(config)
        with self._lock:
            s = self.view["session"]
            if state.interrupts:
                payload = state.interrupts[0].value
                hito = payload["hito"]
                s["current_hito"] = hito
                if payload["type"] == "approve_subtasks":
                    s["phase"] = "awaiting_approval"
                    s["message"] = "Revisa y aprueba las subtareas propuestas por los agentes."
                    self.view["data"][hito] = [_task_for_ui(t) for t in payload["tasks"]]
                else:  # review_hito
                    s["phase"] = "awaiting_review"
                    s["message"] = "Revisa el resultado del hito: apruébalo o pide rehacerlo."
                    s["results"][hito] = payload["result"]
                    s["attempts"][hito] = payload["attempt"]
                    s["can_redo"] = payload["can_redo"]
            elif not state.next:
                s["phase"] = "done"
                s["message"] = "Estudio completado y exportado."
                s["final"] = state.values.get("final")
        self._notify()