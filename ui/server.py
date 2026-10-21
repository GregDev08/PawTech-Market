import asyncio
import json
import websockets
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from agents.schemas import PlanProposal, SubTaskProposal

TASKS_DB = {
    1: [],
    2: [
        {"id": "ST-201", "name": "[Análisis Cuantitativo] Procesamiento de precios y unidades mediante Pandas/MCP", "progress": 0, "status": "waiting_approval"},
        {"id": "ST-202", "name": "[Análisis Visual] Inspección de packaging y etiquetas holísticas", "progress": 0, "status": "waiting_approval"}
    ],
    3: [
        {"id": "ST-301", "name": "[Redacción Estratégica] Síntesis ejecutiva y auditoría de gobernanza", "progress": 0, "status": "waiting_approval"},
        {"id": "ST-302", "name": "[Revisor Crítico] Verificación de fuentes y prevención de alucinaciones", "progress": 0, "status": "waiting_approval"}
    ]
}

CLIENTS = set()

async def notify_clients():
    if CLIENTS:
        message = json.dumps({"type": "STATE_UPDATE", "data": TASKS_DB})
        await asyncio.gather(*[client.send(message) for client in CLIENTS], return_exceptions=True)

async def run_task_progress(hito):
    """Bucle independiente en segundo plano que actualiza el progreso sin depender de conexiones activas."""
    for _ in range(9):
        await asyncio.sleep(0.4)
        for task in TASKS_DB.get(hito, []):
            if task["status"] == "in_progress":
                task["progress"] = min(100, task["progress"] + 10)
                if task["progress"] >= 100:
                    task["status"] = "completed"
        await notify_clients()

async def handle_client(websocket):
    CLIENTS.add(websocket)
    try:
        # Enviar estado inicial al conectar
        await websocket.send(json.dumps({"type": "STATE_UPDATE", "data": TASKS_DB}))
        
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")
            
            if action == "SUBMIT_QUERY":
                user_query = data.get("query", "Estudio de mercado general")
                
                proposal = PlanProposal(
                    niche=user_query,
                    proposed_tasks=[
                        SubTaskProposal(
                            task_id="ST-101",
                            title=f"Rastreo web de competidores: {user_query[:25]}...",
                            description="Investigar ofertas, modelos de suscripción y competidores directos en e-commerce.",
                            category="Investigación Web"
                        ),
                        SubTaskProposal(
                            task_id="ST-102",
                            title="Identificación de tendencias y propuesta de valor",
                            description="Analizar atributos de productos holísticos y posicionamiento en el mercado.",
                            category="Tendencias"
                        )
                    ]
                )
                
                TASKS_DB[1] = [
                    {
                        "id": t.task_id,
                        "name": f"[{t.category}] {t.title} — {t.description}",
                        "progress": 0,
                        "status": "waiting_approval"
                    }
                    for t in proposal.proposed_tasks
                ]
                await notify_clients()
            
            elif action == "START_TASKS":
                hito = int(data.get("hito", 1))
                approved_ids = data.get("approved_ids", [])
                
                for task in TASKS_DB.get(hito, []):
                    if task["id"] in approved_ids:
                        task["status"] = "in_progress"
                        task["progress"] = 10
                    else:
                        task["status"] = "skipped"
                        task["progress"] = 0
                
                await notify_clients()
                
                # Ejecutar el progreso de forma asíncrona e independiente
                asyncio.create_task(run_task_progress(hito))
                    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.remove(websocket)

async def main():
    async with websockets.serve(handle_client, "localhost", 8765):
        print("🌐 Servidor WebSocket activo en ws://localhost:8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())