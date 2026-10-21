import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import asyncio
import websockets
import json

def show():
    st.title("📊 Dashboard de Monitoreo en Tiempo Real")
    st.write("Monitoreo en vivo del progreso de los agentes de la Squad. El estado se actualiza automáticamente.")

    DEFAULT_TASKS = [
        {"task_id": 101, "agent_id": 1, "agent_name": "Investigador/a (Búsqueda)", "message": "Rastrear la web para recopilar datos de competidores.", "status": "waiting_approval", "progress": 0.0},
        {"task_id": 102, "agent_id": 2, "agent_name": "Analista de Datos (Python)", "message": "Ejecutar script de Pandas/Plotly para cifras.", "status": "waiting_approval", "progress": 0.0},
        {"task_id": 103, "agent_id": 3, "agent_name": "Especialista Multimodal", "message": "Analizar gráficos y capturas web.", "status": "waiting_approval", "progress": 0.0},
        {"task_id": 104, "agent_id": 4, "agent_name": "Redactor/a Estratégico/a", "message": "Redactar informe borrador de mercado.", "status": "waiting_approval", "progress": 0.0},
        {"task_id": 105, "agent_id": 5, "agent_name": "Revisor/a Crítico/a (HITL)", "message": "Verificar trazabilidad y autorizar entrega final.", "status": "waiting_approval", "progress": 0.0}
    ]

    if 'agent_data' not in st.session_state or not st.session_state.agent_data:
        st.session_state.agent_data = [dict(t) for t in DEFAULT_TASKS]

    # --- FRAGMENTO EN VIVO (Se actualiza automáticamente cada 1 segundo) ---
    @st.fragment(run_every=1)
    def live_dashboard_section():
        # Consulta rápida al servidor WebSocket para obtener el estado actual
        async def fetch_latest():
            try:
                async with websockets.connect("ws://localhost:8765") as websocket:
                    message = await websocket.recv()
                    tasks = json.loads(message)
                    if isinstance(tasks, list):
                        st.session_state.agent_data = tasks
            except Exception:
                pass  # Si el servidor no responde al instante, mantiene los datos actuales

        try:
            asyncio.run(fetch_latest())
        except RuntimeError:
            pass

        valid_tasks = [t for t in st.session_state.agent_data if isinstance(t, dict)]

        if valid_tasks:
            df = pd.DataFrame(valid_tasks)
            
            if 'agent_name' in df.columns and 'progress' in df.columns and 'status' in df.columns:
                st.subheader("📋 Estado Actual de la Squad (En Vivo)")
                
                fig, ax = plt.subplots(figsize=(10, 4))
                colors = [
                    'green' if s == 'completed' else 
                    'orange' if s == 'in_progress' else 
                    'red' if s == 'failed' else 'gray' 
                    for s in df['status']
                ]
                ax.barh(df['agent_name'], df['progress'], color=colors)
                ax.set_xlim(0, 105)
                ax.set_xlabel('Progreso (%)')
                ax.set_title('Ejecución Autónoma de Agentes')
                st.pyplot(fig)
                plt.close(fig)

                st.dataframe(df[['task_id', 'agent_name', 'status', 'progress', 'message']], use_container_width=True)
                
                st.markdown("---")
                st.subheader("🪵 Consola de Logs")
                logs_text = "\n".join([f"[Tarea {d.get('task_id')}] {d.get('agent_name')} | Estado: {d.get('status')} | Progreso: {d.get('progress')}% | {d.get('message')}" for d in valid_tasks])
                st.text_area("Logs del Sistema", value=logs_text, height=150, key="live_logs")
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Descargar Informe CSV", csv, "informe_agentes.csv", "text/csv")

    # Renderizamos el fragmento autónomo
    live_dashboard_section()

    st.markdown("---")
    if st.button("🧹 Restablecer Tareas"):
        st.session_state.agent_data = [dict(t) for t in DEFAULT_TASKS]
        st.success("¡Tareas restablecidas!")
        st.rerun()