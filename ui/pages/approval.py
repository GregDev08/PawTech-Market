import streamlit as st
import asyncio
import websockets
import json

def send_ws_action(action_type, task_id):
    async def _send():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                await websocket.send(json.dumps({"action": action_type, "task_id": task_id}))
        except Exception as e:
            st.error(f"Error comunicando con el servidor: {e}")
    asyncio.run(_send())

def show():
    st.title("🛡️ Panel de Aprobación (Human-in-the-Loop)")
    st.write("Aprueba las tareas. El servidor WebSocket detectará tu acción y ejecutará el proceso de forma automática.")

    # Inicializar o limpiar datos si están corruptos o no son diccionarios
    if 'agent_data' not in st.session_state or not isinstance(st.session_state.agent_data, list):
        st.session_state.agent_data = []

    # Filtrar estrictamente solo elementos que sean diccionarios válidos y estén esperando aprobación
    pending_actions = [
        t for t in st.session_state.agent_data 
        if isinstance(t, dict) and t.get('status') == 'waiting_approval'
    ]

    if not pending_actions:
        st.success("✅ ¡No hay tareas pendientes de aprobación en este momento! (O espera a sincronizar con el Dashboard)")
    else:
        for task in pending_actions:
            task_id = task.get("task_id")
            with st.container(border=True):
                st.subheader(f"Agente: {task.get('agent_name', 'Desconocido')} (ID: {task_id})")
                st.write(f"**Acción:** {task.get('message', 'Sin mensaje')}")
                st.warning("Estado: ⏸️ En pausa esperando aprobación humana")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Aprobar #{task_id}", key=f"app_{task_id}"):
                        send_ws_action("approve", task_id)
                        task["status"] = "in_progress"
                        task["progress"] = 10.0
                        st.success(f"¡Tarea #{task_id} aprobada! El servidor ha tomado el control.")
                        st.rerun()
                with col2:
                    if st.button(f"❌ Rechazar #{task_id}", key=f"rej_{task_id}"):
                        send_ws_action("reject", task_id)
                        task["status"] = "failed"
                        st.error(f"Tarea #{task_id} rechazada.")
                        st.rerun()