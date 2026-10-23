"""Servidor WebSocket de PawTech-Market: conecta la interfaz con el grafo de agentes.

Antes este servidor inventaba las subtareas y simulaba las barras de progreso.
Ahora cada acción de la interfaz se la paso a StudySession (graph/session.py), que
ejecuta el grafo LangGraph de verdad, y reenvío a la interfaz el estado real.
"""
import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

import websockets

from graph.session import StudySession

# Importar tu logger existente (asegúrate de que logger.py esté accesible en el path)
import logger.logger   

HOST, PORT = "localhost", 8765
CLIENTS: set = set()

# Directorios de salida definidos de forma consistente
OUTPUTS_DIR = ROOT_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)


def save_study_checkpoint(view: dict) -> None:
    """Guarda un registro estructurado con el estado, subtareas y resultados del estudio."""
    checkpoint_file = OUTPUTS_DIR / "study_history.json"
    data = view.get("data", {})
    session_info = view.get("session", {})

    history_record = {
        "updated_at": datetime.now().isoformat(),
        "query": session_info.get("query"),
        "phase": session_info.get("phase"),
        "current_hito": session_info.get("current_hito"),
        "attempts": session_info.get("attempts", {}),
        "tasks_by_hito": data,
        "results_by_hito": session_info.get("results", {}),
    }

    try:
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(history_record, f, indent=2, ensure_ascii=False)
        logging.info(
            f"Checkpoint del estudio actualizado en: {checkpoint_file}"
        )
    except Exception as e:
        logging.error(f"Error al guardar el checkpoint del estudio: {e}")


def _state_message(view: dict) -> str:
    return json.dumps({"type": "STATE_UPDATE", **view}, ensure_ascii=False)


async def broadcast(view: dict) -> None:
    """Envío el estado a todas las pestañas conectadas y guardo el checkpoint."""
    save_study_checkpoint(view)

    if CLIENTS:
        message = _state_message(view)
        await asyncio.gather(
            *[client.send(message) for client in CLIENTS],
            return_exceptions=True,
        )


def make_session(loop: asyncio.AbstractEventLoop) -> StudySession:
    """La sesión avisa desde el hilo del grafo; aquí lo paso al bucle del servidor."""

    def on_change(view: dict) -> None:
        asyncio.run_coroutine_threadsafe(broadcast(view), loop)

    return StudySession(on_change=on_change)


def dispatch(session: StudySession, data: dict) -> None:
    """Traduzco cada acción de la interfaz a una llamada a la sesión."""
    action = data.get("action")
    logging.info(f"Acción recibida desde la interfaz: {action} con datos: {data}")
    if action == "SUBMIT_QUERY":
        session.start(data.get("query", ""))
    elif action == "START_TASKS":
        session.approve_subtasks(
            int(data.get("hito", 1)), data.get("approved_ids", [])
        )
    elif action == "REVIEW_HITO":
        session.review_hito(
            int(data.get("hito", 1)),
            data.get("decision", ""),
            data.get("feedback", ""),
        )
    elif action == "RETRY":
        session.retry()
    elif action == "RESET":
        session.reset()
    else:
        raise ValueError(f"Acción desconocida: {action}")


def make_handler(session: StudySession):
    async def handle_client(websocket):
        CLIENTS.add(websocket)
        try:
            await websocket.send(_state_message(session.snapshot()))
            async for message in websocket:
                try:
                    dispatch(session, json.loads(message))
                except Exception as exc:
                    logging.error(f"Error procesando acción: {exc}")
                    await websocket.send(
                        json.dumps(
                            {"type": "ERROR", "message": str(exc)},
                            ensure_ascii=False,
                        )
                    )
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            CLIENTS.discard(websocket)

    return handle_client


async def main() -> None:
    session = make_session(asyncio.get_running_loop())
    async with websockets.serve(
        make_handler(session), HOST, PORT, max_size=None
    ):
        print(f"🌐 Servidor WebSocket activo en ws://{HOST}:{PORT}")
        logging.info(f"Servidor WebSocket iniciado en ws://{HOST}:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())