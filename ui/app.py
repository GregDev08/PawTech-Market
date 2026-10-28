import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

import streamlit as st
import asyncio
import websockets
import json
import logging

# Importar el logger para registrar la actividad de la interfaz en logs
import logger.logger  

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
if "session" not in st.session_state:
    st.session_state.session = {"phase": "idle", "current_hito": 1, "attempts": {}, "results": {}}


# Función para enviar comandos al servidor WebSocket
def send_ws_payload(action, payload):
    async def _send():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                await websocket.recv()
                payload["action"] = action
                await websocket.send(json.dumps(payload))
                try:
                    reply = json.loads(await asyncio.wait_for(websocket.recv(), timeout=0.5))
                    if reply.get("type") == "ERROR":
                        st.error(reply.get("message"))
                        logging.error(f"Error recibido del servidor WS: {reply.get('message')}")
                except asyncio.TimeoutError:
                    pass
        except Exception as e:
            st.error(f"Error de conexión WebSocket: {e}")
            logging.error(f"Error de conexión WebSocket en UI: {e}")
    asyncio.run(_send())


def sess():
    return st.session_state.session


def result_of(hito_num):
    return (sess().get("results") or {}).get(str(hito_num))


def attempt_of(hito_num):
    return (sess().get("attempts") or {}).get(str(hito_num), 1)


def fetch_state():
    async def _listen():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                msg = await websocket.recv()
                data = json.loads(msg)
                if data.get("type") == "STATE_UPDATE":
                    raw_data = data.get("data", {})
                    st.session_state.tasks_state = {int(k): v for k, v in raw_data.items()}
                    st.session_state.session = data.get("session", st.session_state.session)
                    s = st.session_state.session
                    st.session_state.current_stage = 4 if s.get("phase") == "done" else s.get("current_hito", 1)
                    st.session_state.user_query = s.get("query") or st.session_state.user_query
        except Exception as e:
            logging.error("Error al obtener el estado por WebSocket: %s", e, exc_info=True)
            st.error(f"No se pudo conectar con el servidor WebSocket: {e}")

    try:
        asyncio.run(_listen())
    except RuntimeError as e:
        logging.error("No se pudo ejecutar el listener WebSocket: %s", e, exc_info=True)
        st.error(f"No se pudo consultar el estado del servidor WebSocket: {e}")


fetch_state()

st.markdown("---")

# ==========================================
# CUADRO DE TEXTO INICIAL (PETICIÓN DE TAREA)
# ==========================================
st.subheader("💡 Petición de Investigación (Hito 1 - Inicialización)")

# 1. El cuadro de texto va primero
user_input = st.text_area(
    "¿Qué deseas que investiguen los agentes?",
    value=st.session_state.user_query,
    placeholder="Ej: Análisis de competidores, precios de alimentos holísticos y gadgets para mascotas en España...",
    height=80,
    disabled=(sess().get("phase") != "idle")
)

# 2. Opciones de voz y botón de envío unificadas cuando está en fase 'idle'
if sess().get("phase") == "idle":
    st.markdown("---")
    st.write("🎙️ **O si lo prefieres, graba una nota de voz:**")
    audio_value = st.audio_input("Graba tu consulta")

    if audio_value is not None:
        # Guardamos temporalmente el audio grabado para transcribirlo
        temp_audio_path = Path("outputs/temp_query.wav")
        temp_audio_path.parent.mkdir(exist_ok=True)
        temp_audio_path.write_bytes(audio_value.read())
        
        # Llamamos a faster-whisper para convertir la voz en texto
        try:
            from graph.voice_utils import audio_to_text
            transcribed_text = audio_to_text(str(temp_audio_path))
            
            if transcribed_text and transcribed_text != st.session_state.user_query:
                st.session_state.user_query = transcribed_text
                st.success(f"🎙️ Voz transcrita con éxito: '{transcribed_text}'")
                st.rerun() # Recarga para que el texto aparezca automáticamente en el st.text_area
        except Exception as e:
            st.error(f"Error al transcribir el audio: {e}")

    # 3. Único botón de envío al final de las opciones
    if st.button("🚀 Enviar Petición al Investigador"):
        if not user_input.strip():
            st.warning("Por favor, introduce una consulta válida o graba un audio.")
        else:
            st.session_state.user_query = user_input
            logging.info(f"UI: Usuario envió consulta de investigación -> {user_input}")
            send_ws_payload("SUBMIT_QUERY", {"query": user_input})
            st.success("¡Petición enviada! El agente planificador está preparando las subtareas…")
            st.rerun()

st.markdown("---")


def render_result(hito_num):
    r = result_of(hito_num)
    if not r:
        return

    # Clave de sesión única para mantener el audio visible en este hito
    audio_session_key = f"audio_bytes_hito_{hito_num}"
    if audio_session_key not in st.session_state:
        st.session_state[audio_session_key] = None

    texto_para_voz = ""

    # 1. HITO 1: INVESTIGACIÓN
    if r["kind"] == "research":
        st.write(r["summary"])
        texto_para_voz = r["summary"]

        rows = [{"Marca": c["brand"], "Producto": c["product"], "Tienda": c.get("store"),
                 "Precio (€)": c.get("price_eur"), "Tamaño (kg)": c.get("size_kg"),
                 "€/kg": c.get("price_per_kg")} for c in r["competitors"]]
        if rows:
            st.dataframe(rows, hide_index=True)
        if r.get("cheapest"):
            c = r["cheapest"]
            st.success(f"Más barato por kg: **{c['brand']} {c['product']}** ({c.get('store')}) → {c['price_per_kg']} €/kg")
        st.caption(f"Precios comparables: {r['comparable_prices']} · duplicados quitados: {r['duplicates_removed']}")

    # 2. HITO 2: VALIDACIÓN CUANTITATIVA Y VISUAL
    elif r["kind"] == "validation":
        stats = r["quantitative_summary"]["estadisticas"]
        s = (stats.get("summary") or {}).get("precio_eur_kg")
        if s:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Media €/kg", f"{s['mean']:.2f}")
            c2.metric("Mínimo", f"{s['min']:.2f}")
            c3.metric("Máximo", f"{s['max']:.2f}")
            c4.metric("Desviación", "—" if s["std"] is None else f"{s['std']:.2f}")
            st.caption(f"Calculado vía {stats.get('via')} con {stats.get('row_count')} precios")
            
            # Texto preparado para el audio del Hito 2
            interpretacion = r['quantitative_summary'].get('interpretacion', '')
            texto_para_voz = f"Validación cuantitativa del Hito 2. La media de precios es de {s['mean']:.2f} euros por kilo. {interpretacion}"
        else:
            st.warning(stats.get("aviso", "Sin estadísticas."))
            texto_para_voz = "Validación del Hito 2 completada sin estadísticas suficientes."
            
        with st.expander("Interpretación cuantitativa"):
            st.write(r["quantitative_summary"].get("interpretacion") or "—")
        with st.expander("Hallazgos visuales"):
            st.write(r["visual_findings"])

    # 3. HITO 3: INFORME Y AUDITORÍA
    elif r["kind"] == "report":
        rep = r["report"]
        st.markdown(f"#### {rep['title']}")
        st.write(rep["executive_summary"])
        st.markdown("**Distribución de precios** (cifras calculadas por código)")
        st.write(rep["price_distribution_summary"])
        st.markdown("**Recomendaciones**")
        for rec in rep["recommendations"]:
            st.markdown(f"- {rec}")
        verdict = r.get("audit_verdict")
        (st.success if verdict == "APROBADO" else st.warning)(f"Veredicto del revisor crítico: {verdict}")
        st.caption("Si apruebas, autorizas la exportación del informe a outputs/.")

        # Texto preparado para el audio del Hito 3
        texto_para_voz = f"Informe final: {rep['title']}. {rep['executive_summary']}"

    # ==========================================
    # 🔊 SECCIÓN DE AUDIO (DISPONIBLE PARA TODOS LOS HITOS)
    # ==========================================
    if texto_para_voz:
        col_btn, _ = st.columns([1, 2])
        with col_btn:
            if st.button("🔊 Escuchar resumen en voz alta", key=f"tts_h{hito_num}"):
                with st.spinner("Generando audio con Edge-TTS..."):
                    audio_output_path = Path(f"outputs/resumen_hito_{hito_num}.mp3")
                    audio_output_path.parent.mkdir(exist_ok=True)
                    
                    try:
                        from graph.voice_utils import text_to_audio
                    except ImportError:
                        from graph.voice_utils import generate_tts_file as text_to_audio
                    
                    # Generamos el archivo de audio
                    text_to_audio(texto_para_voz, str(audio_output_path))
                    
                    # Si existe, leemos los bytes y los guardamos en la sesión
                    if audio_output_path.exists():
                        st.session_state[audio_session_key] = audio_output_path.read_bytes()
                    else:
                        st.error("No se pudo generar el archivo de audio.")

        # Si ya hay audio en la sesión para este hito, mostramos el reproductor fijo
        if st.session_state[audio_session_key] is not None:
            st.audio(st.session_state[audio_session_key], format="audio/mp3")

    # Control de errores en subtareas
    for t in r.get("subtasks", []):
        if t.get("status") == "failed":
            st.error(f"{t['id']} falló: {t.get('error')}")


# ==========================================
# FRAGMENTO REACTIVO EN VIVO (WEBSOCKETS + UI)
# ==========================================
@st.fragment(run_every=0.8)
def live_dashboard_fragment():
    fetch_state()

    s = sess()
    if s.get("phase") == "error":
        st.error(f"⚠️ {s.get('message')}\n\n{s.get('error')}")
        if st.button("🔁 Reintentar", key="btn_retry"):
            logging.info("UI: Usuario hizo clic en Reintentar.")
            send_ws_payload("RETRY", {})
            st.rerun()
    elif s.get("phase") in ("planning", "executing", "finalizing"):
        st.info(f"⏳ {s.get('message')}")

    def render_hito_block(hito_num, hito_title, description):
        st.subheader(f"📌 {hito_title}")
        st.write(description)

        tasks = st.session_state.tasks_state.get(hito_num, [])
        stage = st.session_state.current_stage
        phase = sess().get("phase")
        attempt = attempt_of(hito_num)
        max_attempts = sess().get("max_attempts", 3)

        if stage == hito_num:
            if attempt > 1:
                st.caption(f"Intento {attempt} de {max_attempts}")

            if not tasks:
                st.info("Esperando a que se envíe la petición de investigación para generar las subtareas..."
                        if phase == "idle" else "El agente planificador está proponiendo subtareas…")
                return

            if phase == "awaiting_approval":
                st.markdown("**Selecciona las subtareas que deseas autorizar para este hito:**")
                approved_ids = []
                for task in tasks:
                    is_checked = st.checkbox(
                        f"**{task['name']}**",
                        value=(task["status"] != "skipped"),
                        key=f"chk_h{hito_num}_a{attempt}_{task['id']}"
                    )
                    if is_checked:
                        approved_ids.append(task["id"])

                col_b1, col_b2 = st.columns([1, 4])
                with col_b1:
                    if st.button(f"✅ Autorizar y Ejecutar", key=f"btn_run_{hito_num}_a{attempt}"):
                        if not approved_ids:
                            st.warning("Selecciona al menos una subtarea.")
                        else:
                            logging.info(f"UI: Usuario autorizó subtareas para el Hito {hito_num}: {approved_ids}")
                            send_ws_payload("START_TASKS", {"hito": hito_num, "approved_ids": approved_ids})
                            st.success(f"¡Hito {hito_num} en ejecución por los agentes!")
                            st.rerun()

            st.markdown("**Progreso de las subtareas en tiempo real:**")
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
                    elif task["status"] == "skipped":
                        st.warning("Omitida")
                    elif task["status"] == "failed":
                        st.error("Falló")
                    elif task["status"] == "pending":
                        st.caption("En cola")

            if phase == "awaiting_review":
                st.markdown("---")
                st.markdown(f"### 📋 Resultado Generado por los Agentes (Hito {hito_num})")
                render_result(hito_num)

                can_redo = sess().get("can_redo", True)
                col_ctrl1, col_ctrl2 = st.columns(2)
                with col_ctrl1:
                    feedback = st.text_input("¿Qué quieres que cambien los agentes?",
                                             key=f"fb_{hito_num}_a{attempt}", disabled=not can_redo)
                    if st.button(f"🔄 Rehacer Hito {hito_num}", key=f"btn_redo_{hito_num}_a{attempt}",
                                 disabled=not can_redo):
                        logging.info(f"UI: Usuario solicitó rehacer Hito {hito_num} con feedback: {feedback}")
                        send_ws_payload("REVIEW_HITO", {"hito": hito_num, "decision": "redo", "feedback": feedback})
                        st.rerun()
                    if not can_redo:
                        st.caption(f"Límite de {max_attempts} intentos alcanzado: solo se puede aprobar.")
                with col_ctrl2:
                    if hito_num < 3:
                        if st.button(f"➡️ Pasar al Siguiente Hito", key=f"btn_next_{hito_num}_a{attempt}"):
                            logging.info(f"UI: Usuario aprobó el Hito {hito_num} y pasó al siguiente.")
                            send_ws_payload("REVIEW_HITO", {"hito": hito_num, "decision": "approve"})
                            st.rerun()
                    else:
                        if st.button(f"🎉 Finalizar Estudio de Mercado", key=f"btn_finish_a{attempt}"):
                            logging.info("UI: Usuario finalizó el estudio de mercado completo.")
                            send_ws_payload("REVIEW_HITO", {"hito": hito_num, "decision": "approve"})
                            st.rerun()

        elif stage > hito_num:
            st.success(f"✅ **{hito_title} completado y validado.**")
            with st.expander(f"Ver resultados y subtareas del Hito {hito_num}", expanded=False):
                render_result(hito_num)
        else:
            st.markdown("*Paso bloqueado. Completa los hitos anteriores.*")

        st.markdown("---")

    render_hito_block(1, "Hito 1: Planificación y Aprobación de Subtareas", "El Agente Investigador desglosa la consulta utilizando esquemas tipados.")
    render_hito_block(2, "Hito 2: Validación Cuantitativa (MCP) y Visual", "El Analista de Datos y Especialista Multimodal procesan métricas e imágenes.")
    render_hito_block(3, "Hito 3: Aprobación Final de Informe y Automatización", "El Redactor Estratégico y Revisor Crítico consolidan el entregable final.")

    if st.session_state.current_stage > 3:
        if not st.session_state.get("celebrated"):
            st.balloons()
            st.session_state.celebrated = True
        st.success("🏆 **¡Proceso completado de extremo a extremo!** Se han superado los 3 Hitos con éxito.")

        final = sess().get("final") or {}
        final_md = final.get("markdown") or f"# Estudio de Mercado: {st.session_state.user_query}\n"

        if "audio_final_generado" not in st.session_state:
            st.session_state.audio_final_generado = False
        # 🔊 Botón para escuchar el resumen ejecutivo final
        if st.button("🔊 Escuchar Informe Final en Voz"):
            with st.spinner("Sintetizando voz del informe..."):
                audio_output_path = Path("outputs/informe_final.mp3")
                from graph.voice_utils import text_to_speech_file
                
                # Cogemos las primeras frases del resumen ejecutivo para que no sea eterno
                rep_data = sess().get("results", {}).get("3", {}).get("report", {})
                texto_a_leer = rep_data.get("executive_summary", "Estudio de mercado completado con éxito.")

                text_to_speech_file(texto_a_leer, str(audio_output_path))
                
                if audio_output_path.exists():
                    st.session_state.audio_final_generado = True
                    st.success("¡Audio generado con éxito!")
                else:
                    st.error("No se pudo generar el archivo de audio.")

        # 3. Si ya se generó, mostramos el reproductor SIEMPRE (fuera del botón)
        if st.session_state.audio_final_generado:
            audio_output_path = Path("outputs/informe_final.mp3")
            if audio_output_path.exists():
                audio_bytes = audio_output_path.read_bytes()
                st.audio(audio_bytes, format="audio/mp3")

        st.download_button(
            label="📥 Descargar Informe Final (.md)",
            data=final_md,
            file_name="informe_pawtech_market.md",
            mime="text/markdown"
        )
        if final.get("files"):
            st.caption("También guardado en: " + " · ".join(final["files"]))

        if st.button("🔄 Iniciar Nuevo Estudio de Mercado"):
            logging.info("UI: Reiniciando estudio de mercado completo.")
            send_ws_payload("RESET", {})
            st.session_state.current_stage = 1
            st.session_state.user_query = ""
            st.session_state.tasks_state = {1: [], 2: [], 3: []}
            st.session_state.celebrated = False
            st.rerun()

live_dashboard_fragment()