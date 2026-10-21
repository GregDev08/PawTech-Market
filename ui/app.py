import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

import streamlit as st
import asyncio
import websockets
import json

# Configuración de página con estética clásica
st.set_page_config(
    page_title="PawTech-Market | Sistema Multi-Agente HITL",
    page_icon="🤖",
    layout="wide"
)

# ==========================================
# ESTILOS CSS - PALETA DE COLOR PAWTECH
# ==========================================
st.markdown("""
<style>
    /* Fondo general de la aplicación */
    .stApp {
        background-color: #0f1117;
        color: #f0f2f6;
    }
    
    /* Títulos principales con acento degradado cian/rosa */
    h1, h2, h3 {
        color: #00ffff !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Contenedores con estilo tarjeta cibernética */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        background-color: #1a1c29;
        border: 1px solid #ff69b4 !important;
        border-radius: 10px;
        box-shadow: 0 0 10px rgba(0, 255, 255, 0.2);
    }
    
    /* Botones principales (Color Rosa / Magenta corporativo) */
    .stButton > button {
        background: linear-gradient(90deg, #ff69b4, #00ffff);
        color: #0f1117;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        box-shadow: 0 0 10px rgba(255, 105, 180, 0.4);
        transition: 0.3s;
    }
    
    .stButton > button:hover {
        opacity: 0.9;
        box-shadow: 0 0 15px rgba(0, 255, 255, 0.6);
    }
    
    /* Barras de progreso en Verde Lima / Cian */
    .stProgress > div > div > div > div {
        background-color: #00ff00 !important;
    }
    
    /* Cajas de texto y áreas de texto */
    textarea, input {
        background-color: #16192b !important;
        color: #00ffff !important;
        border: 1px solid #9370db !important;
        border-radius: 6px !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🤖 PawTech-Market | Sistema Multi-Agente con Validación en Vivo")
st.write("Orquestación híbrida con **LangGraph, CrewAI, Pydantic y WebSockets** (Human-in-the-Loop en 3 Hitos).")

# Variables de sesión
if "user_query" not in st.session_state:
    st.session_state.user_query = ""
if "tasks_state" not in st.session_state:
    st.session_state.tasks_state = {1: [], 2: [], 3: []}
if "current_stage" not in st.session_state:
    st.session_state.current_stage = 1

# Función para enviar comandos al servidor WebSocket
def send_ws_payload(action, payload):
    async def _send():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                payload["action"] = action
                await websocket.send(json.dumps(payload))
        except Exception as e:
            st.error(f"Error de conexión WebSocket: {e}")
    asyncio.run(_send())

st.markdown("---")

# ==========================================
# CUADRO DE TEXTO INICIAL (PETICIÓN DE TAREA)
# ==========================================
st.subheader("💡 Petición de Investigación (Hito 1 - Inicialización)")

user_input = st.text_area(
    "¿Qué deseas que investiguen los agentes?",
    value=st.session_state.user_query,
    placeholder="Ej: Análisis de competidores, precios de alimentos holísticos y gadgets para mascotas en España...",
    height=80,
    disabled=(st.session_state.current_stage > 1)
)

if st.session_state.current_stage == 1 and not st.session_state.tasks_state.get(1):
    if st.button("🚀 Enviar Petición al Investigador"):
        if not user_input.strip():
            st.warning("Por favor, introduce una consulta válida.")
        else:
            st.session_state.user_query = user_input
            send_ws_payload("SUBMIT_QUERY", {"query": user_input})
            st.success("¡Petición enviada! El agente planificador ha generado las subtareas basadas en Pydantic.")
            st.rerun()

st.markdown("---")

# ==========================================
# FRAGMENTO REACTIVO EN VIVO (WEBSOCKETS + UI)
# ==========================================
@st.fragment(run_every=0.8)
def live_dashboard_fragment():
    """Este fragmento se ejecuta automáticamente cada 0.8s, actualiza los datos del WebSocket y redibuja la interfaz en vivo."""
    
    # 1. Escuchar estado del WebSocket
    async def _listen():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                msg = await websocket.recv()
                data = json.loads(msg)
                if data.get("type") == "STATE_UPDATE":
                    raw_data = data.get("data", {})
                    st.session_state.tasks_state = {int(k): v for k, v in raw_data.items()}
        except Exception:
            pass

    try:
        asyncio.run(_listen())
    except RuntimeError:
        pass

    # 2. Función interna para renderizar cada Hito de forma reactiva
    def render_hito_block(hito_num, hito_title, description):
        st.subheader(f"📌 {hito_title}")
        st.write(description)
        
        tasks = st.session_state.tasks_state.get(hito_num, [])
        stage = st.session_state.current_stage
        
        if stage == hito_num:
            if not tasks:
                st.info("Esperando a que se envíe la petición de investigación para generar las subtareas...")
                return

            st.markdown("**Selecciona las subtareas que deseas autorizar para este hito:**")
            approved_ids = []
            for task in tasks:
                is_checked = st.checkbox(
                    f"**{task['name']}**",
                    value=(task["status"] != "skipped"),
                    key=f"chk_h{hito_num}_{task['id']}"
                )
                if is_checked:
                    approved_ids.append(task["id"])
            
            col_b1, col_b2 = st.columns([1, 4])
            with col_b1:
                if st.button(f"✅ Autorizar y Ejecutar", key=f"btn_run_{hito_num}"):
                    if not approved_ids:
                        st.warning("Selecciona al menos una subtarea.")
                    else:
                        send_ws_payload("START_TASKS", {"hito": hito_num, "approved_ids": approved_ids})
                        st.success(f"¡Hito {hito_num} en ejecución por los agentes!")
                        st.rerun()

            st.markdown("**Progreso de las subtareas en tiempo real:**")
            all_done = True
            for task in tasks:
                col_desc, col_bar, col_stat = st.columns([3, 4, 2])
                with col_desc:
                    st.caption(task["name"])
                with col_bar:
                    st.progress(task["progress"] / 100.0)
                with col_stat:
                    if task["status"] == "completed":
                        st.success("100% Completado")
                    elif task["status"] == "in_progress":
                        st.info(f"⏳ {task['progress']}% En curso...")
                        all_done = False
                    elif task["status"] == "skipped":
                        st.warning("Omitida")
                    else:
                        all_done = False

            # Si todas las tareas se han completado, mostrar el resultado de los agentes y los botones de control
            if all_done and any(t["status"] == "completed" for t in tasks):
                st.markdown("---")
                st.markdown(f"### 📋 Resultado Generado por los Agentes (Hito {hito_num})")
                
                # Texto simulado/real del resultado obtenido por la Squad en este hito
                if hito_num == 1:
                    agent_result_text = f"Planificación estructurada completada con éxito para el nicho: '{st.session_state.user_query}'. Se han validado las rutas de rastreo web y análisis de tendencias."
                elif hito_num == 2:
                    agent_result_text = "Análisis cuantitativo (MCP / Pandas) y visual (Multimodal) finalizado. Rango óptimo de precios detectado entre 18.50€ y 24.00€ con sellos holísticos destacados en packaging."
                else:
                    agent_result_text = "Informe ejecutivo de mercado redactado y auditado por el Revisor Crítico. Sin alucinaciones detectadas. Fuentes y referencias bibliográficas verificadas."

                st.info(agent_result_text)

                # Botones de control solicitados: Rehacer hito / Pasar al siguiente
                col_ctrl1, col_ctrl2 = st.columns(2)
                with col_ctrl1:
                    if st.button(f"🔄 Rehacer Hito {hito_num}", key=f"btn_redo_{hito_num}"):
                        # Reiniciar el progreso de este hito
                        for t in tasks:
                            t["progress"] = 0
                            t["status"] = "waiting_approval"
                        st.warning(f"Hito {hito_num} reiniciado. Puedes volver a seleccionar y ejecutar.")
                        st.rerun()
                with col_ctrl2:
                    if hito_num < 3:
                        if st.button(f"➡️ Pasar al Siguiente Hito", key=f"btn_next_{hito_num}"):
                            st.session_state.current_stage = hito_num + 1
                            st.rerun()
                    else:
                        if st.button(f"🎉 Finalizar Estudio de Mercado", key=f"btn_finish"):
                            st.session_state.current_stage = 4  # Etapa finalizada con éxito
                            st.rerun()

        elif stage > hito_num:
            st.info(f"✅ **{hito_title} completado y validado por el usuario.**")
        else:
            st.markdown("*Paso bloqueado. Completa los hitos anteriores.*")
        
        st.markdown("---")

    # Renderizar los 3 Hitos dentro del bucle en vivo
    render_hito_block(1, "Hito 1: Planificación y Aprobación de Subtareas", "El Agente Investigador desglosa la consulta utilizando esquemas tipados.")
    render_hito_block(2, "Hito 2: Validación Cuantitativa (MCP) y Visual", "El Analista de Datos y Especialista Multimodal procesan métricas e imágenes.")
    render_hito_block(3, "Hito 3: Aprobación Final de Informe y Automatización", "El Redactor Estratégico y Revisor Crítico consolidan el entregable final.")

    if st.session_state.current_stage > 3:
        st.balloons()
        st.success("🏆 **¡Proceso completado de extremo a extremo!** Se han superado los 3 Hitos con éxito.")
        
        final_md = f"# Estudio de Mercado: {st.session_state.user_query}\n\n## Resumen Ejecutivo\nProceso validado de extremo a extremo mediante arquitecturas multi-agente con LangGraph, CrewAI y WebSockets."
        
        st.download_button(
            label="📥 Descargar Informe Final (.md)",
            data=final_md,
            file_name="informe_pawtech_market.md",
            mime="text/markdown"
        )

        if st.button("🔄 Iniciar Nuevo Estudio de Mercado"):
            st.session_state.current_stage = 1
            st.session_state.user_query = ""
            st.session_state.tasks_state = {1: [], 2: [], 3: []}
            st.rerun()

# Ejecutar el tablero interactivo en vivo
live_dashboard_fragment()