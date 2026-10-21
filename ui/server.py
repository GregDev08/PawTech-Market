"""Servidor WebSocket de PawTech-Market: conecta la interfaz con el grafo de agentes.

Antes este servidor inventaba las subtareas y simulaba las barras de progreso.
Ahora cada acción de la interfaz se la paso a StudySession (graph/session.py), que
ejecuta el grafo LangGraph de verdad, y reenvío a la interfaz el estado real.

Contrato de mensajes (detallado en docs/contrato_websocket.md):

  Servidor → interfaz
    {"type": "STATE_UPDATE", "data": {...}, "session": {...}}   cada vez que cambia algo
    {"type": "ERROR", "message": str}                            una acción no válida

  Interfaz → servidor
    {"action": "SUBMIT_QUERY", "query": str}
    {"action": "START_TASKS", "hito": int, "approved_ids": [str]}
    {"action": "REVIEW_HITO", "hito": int, "decision": "approve" | "redo", "feedback": str}
    {"action": "RETRY"}
    {"action": "RESET"}

Sin gastar tokens de Groq:  FAKE_LLM=1 python ui/server.py
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import websockets

from graph.session import StudySession

HOST, PORT = "localhost", 8765
CLIENTS: set = set()


def _state_message(view: dict) -> str:
    return json.dumps({"type": "STATE_UPDATE", **view}, ensure_ascii=False)


async def broadcast(view: dict) -> None:
    """Envío el estado a todas las pestañas conectadas."""
    if CLIENTS:
        message = _state_message(view)
        await asyncio.gather(*[client.send(message) for client in CLIENTS], return_exceptions=True)


def make_session(loop: asyncio.AbstractEventLoop) -> StudySession:
    """La sesión avisa desde el hilo del grafo; aquí lo paso al bucle del servidor."""
    def on_change(view: dict) -> None:
        asyncio.run_coroutine_threadsafe(broadcast(view), loop)
    return StudySession(on_change=on_change)


def dispatch(session: StudySession, data: dict) -> None:
    """Traduzco cada acción de la interfaz a una llamada a la sesión."""
    action = data.get("action")
    if action == "SUBMIT_QUERY":
        session.start(data.get("query", ""))
    elif action == "START_TASKS":
        session.approve_subtasks(int(data.get("hito", 1)), data.get("approved_ids", []))
    elif action == "REVIEW_HITO":
        session.review_hito(int(data.get("hito", 1)), data.get("decision", ""), data.get("feedback", ""))
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
            # Al conectar, la interfaz recibe el estado actual (así lo leía ya app.py)
            await websocket.send(_state_message(session.snapshot()))
            async for message in websocket:
                try:
                    dispatch(session, json.loads(message))
                except Exception as exc:  # acción no válida: se lo digo a la interfaz, sin caerme
                    await websocket.send(json.dumps({"type": "ERROR", "message": str(exc)}, ensure_ascii=False))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            CLIENTS.discard(websocket)
    return handle_client


async def main() -> None:
    session = make_session(asyncio.get_running_loop())
    async with websockets.serve(make_handler(session), HOST, PORT, max_size=None):
        print(f"🌐 Servidor WebSocket activo en ws://{HOST}:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())