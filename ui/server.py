import asyncio
import json
import websockets

INITIAL_TASKS = [
    {"task_id": 101, "agent_id": 1, "agent_name": "Investigador/a (Búsqueda)", "message": "Rastrear la web para recopilar datos de competidores.", "status": "waiting_approval", "progress": 0.0},
    {"task_id": 102, "agent_id": 2, "agent_name": "Analista de Datos (Python)", "message": "Ejecutar script de Pandas/Plotly para cifras.", "status": "waiting_approval", "progress": 0.0},
    {"task_id": 103, "agent_id": 3, "agent_name": "Especialista Multimodal", "message": "Analizar gráficos y capturas web.", "status": "waiting_approval", "progress": 0.0},
    {"task_id": 104, "agent_id": 4, "agent_name": "Redactor/a Estratégico/a", "message": "Redactar informe borrador de mercado.", "status": "waiting_approval", "progress": 0.0},
    {"task_id": 105, "agent_id": 5, "agent_name": "Revisor/a Crítico/a (HITL)", "message": "Verificar trazabilidad y autorizar entrega final.", "status": "waiting_approval", "progress": 0.0}
]

current_tasks = [dict(t) for t in INITIAL_TASKS]

async def handler(websocket):
    # Tarea para escuchar comandos de aprobación desde la interfaz
    async def listen_to_ui():
        global current_tasks
        try:
            async for message in websocket:
                data = json.loads(message)
                action = data.get("action")
                task_id = data.get("task_id")

                for task in current_tasks:
                    if task["task_id"] == task_id:
                        if action == "approve":
                            task["status"] = "in_progress"
                            task["progress"] = 10.0
                            task["message"] = task["message"].split(" ➔")[0] + " ➔ [Aprobado: Ejecutando...]"
                        elif action == "reject":
                            task["status"] = "failed"
                            task["progress"] = 0.0
                            task["message"] = task["message"].split(" ➔")[0] + " ➔ [Rechazado]"
        except websockets.exceptions.ConnectionClosed:
            pass

    asyncio.create_task(listen_to_ui())

    # Bucle principal del servidor: actualiza el progreso automáticamente cada segundo
    while True:
        for task in current_tasks:
            if task["status"] == "in_progress":
                if task["progress"] < 100.0:
                    task["progress"] = min(100.0, round(task["progress"] + 20.0, 1))
                    if task["progress"] == 100.0:
                        task["status"] = "completed"
                        task["message"] = task["message"].split(" ➔")[0] + " ➔ [¡Completado con éxito!]"

        try:
            # Transmite el estado actual a todos los clientes conectados
            await websocket.send(json.dumps(current_tasks))
        except websockets.exceptions.ConnectionClosed:
            break

        await asyncio.sleep(1.0) # El servidor avanza solo cada 1 segundo

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("Servidor WebSocket automático activo en ws://localhost:8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())