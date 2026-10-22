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
# [Adriana → Josema] Nuevo: aquí guardo el bloque "session" que ahora manda el servidor
# (fase, intento, resultados reales, informe final…). Ver docs/contrato_websocket.md.
if "session" not in st.session_state:
    st.session_state.session = {"phase": "idle", "current_hito": 1, "attempts": {}, "results": {}}


# Función para enviar comandos al servidor WebSocket
def send_ws_payload(action, payload):
    async def _send():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                await websocket.recv()  # [Adriana → Josema] el servidor manda el estado al conectar: lo descarto
                payload["action"] = action
                await websocket.send(json.dumps(payload))
                # [Adriana → Josema] Nuevo: si la acción no es válida (p. ej. pulsar dos veces),
                # el servidor responde {"type": "ERROR"} y lo enseño en vez de fallar en silencio.
                try:
                    reply = json.loads(await asyncio.wait_for(websocket.recv(), timeout=0.5))
                    if reply.get("type") == "ERROR":
                        st.error(reply.get("message"))
                except asyncio.TimeoutError:
                    pass
        except Exception as e:
            st.error(f"Error de conexión WebSocket: {e}")
    asyncio.run(_send())


# [Adriana → Josema] Nuevo: pequeñas funciones para leer el bloque "session".
# JSON convierte las claves numéricas en texto, por eso uso str(hito).
def sess():
    return st.session_state.session


def result_of(hito_num):
    return (sess().get("results") or {}).get(str(hito_num))


def attempt_of(hito_num):
    return (sess().get("attempts") or {}).get(str(hito_num), 1)


# [Adriana → Josema] Tu _listen() lo he sacado del fragmento a esta función para llamarla
# también al principio de la página: así el cuadro de petición sabe si el estudio ya arrancó
# (antes el botón "Enviar" seguía visible porque esa parte leía el estado antiguo).
def fetch_state():
    async def _listen():
        try:
            async with websockets.connect("ws://localhost:8765") as websocket:
                msg = await websocket.recv()
                data = json.loads(msg)
                if data.get("type") == "STATE_UPDATE":
                    raw_data = data.get("data", {})
                    st.session_state.tasks_state = {int(k): v for k, v in raw_data.items()}
                    # [Adriana → Josema] Nuevo: guardo también "session" y saco de ahí el hito actual.
                    # Antes current_stage lo cambiaban los botones en local; ahora manda el grafo,
                    # así si se recarga la página o se abre otra pestaña se ve lo mismo.
                    st.session_state.session = data.get("session", st.session_state.session)
                    s = st.session_state.session
                    st.session_state.current_stage = 4 if s.get("phase") == "done" else s.get("current_hito", 1)
                    st.session_state.user_query = s.get("query") or st.session_state.user_query
        except Exception:
            pass

    try:
        asyncio.run(_listen())
    except RuntimeError:
        pass


fetch_state()

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
    disabled=(sess().get("phase") != "idle")  # [Adriana → Josema] se bloquea en cuanto arranca el estudio
)

# [Adriana → Josema] Antes el botón dependía de si había subtareas en local; ahora de la fase real del servidor.
if sess().get("phase") == "idle":
    if st.button("🚀 Enviar Petición al Investigador"):
        if not user_input.strip():
            st.warning("Por favor, introduce una consulta válida.")
        else:
            st.session_state.user_query = user_input
            send_ws_payload("SUBMIT_QUERY", {"query": user_input})
            # [Adriana → Josema] Ya no digo "ha generado las subtareas": ahora el planificador
            # tarda unos segundos de verdad. Las subtareas aparecen solas cuando llegan.
            st.success("¡Petición enviada! El agente planificador está preparando las subtareas…")
            st.rerun()

st.markdown("---")


# ==========================================
# [Adriana → Josema] Nuevo: cómo pintar el resultado REAL de cada hito.
# Antes eran tres textos fijos ("Rango óptimo entre 18.50€ y 24.00€…").
# Ahora cada hito trae su resultado en session.results con un "kind" distinto.
# ==========================================
def render_result(hito_num):
    r = result_of(hito_num)
    if not r:
        return
    if r["kind"] == "research":  # Hito 1: productos encontrados, con €/kg calculado por código
        st.write(r["summary"])
        rows = [{"Marca": c["brand"], "Producto": c["product"], "Tienda": c.get("store"),
                 "Precio (€)": c.get("price_eur"), "Tamaño (kg)": c.get("size_kg"),
                 "€/kg": c.get("price_per_kg")} for c in r["competitors"]]
        if rows:
            st.dataframe(rows, hide_index=True)
        if r.get("cheapest"):
            c = r["cheapest"]
            st.success(f"Más barato por kg: **{c['brand']} {c['product']}** ({c.get('store')}) → {c['price_per_kg']} €/kg")
        st.caption(f"Precios comparables: {r['comparable_prices']} · duplicados quitados: {r['duplicates_removed']}")

    elif r["kind"] == "validation":  # Hito 2: estadísticas de la herramienta MCP de Luis
        stats = r["quantitative_summary"]["estadisticas"]
        s = (stats.get("summary") or {}).get("precio_eur_kg")
        if s:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Media €/kg", f"{s['mean']:.2f}")
            c2.metric("Mínimo", f"{s['min']:.2f}")
            c3.metric("Máximo", f"{s['max']:.2f}")
            c4.metric("Desviación", "—" if s["std"] is None else f"{s['std']:.2f}")
            st.caption(f"Calculado vía {stats.get('via')} con {stats.get('row_count')} precios")
        else:
            st.warning(stats.get("aviso", "Sin estadísticas."))
        with st.expander("Interpretación cuantitativa"):
            st.write(r["quantitative_summary"].get("interpretacion") or "—")
        with st.expander("Hallazgos visuales"):
            st.write(r["visual_findings"])

    elif r["kind"] == "report":  # Hito 3: el informe y el veredicto del revisor
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

    # Subtareas que fallaron (p. ej. límite de Groq): se ven, no se esconden
    for t in r.get("subtasks", []):
        if t.get("status") == "failed":
            st.error(f"{t['id']} falló: {t.get('error')}")


# ==========================================
# FRAGMENTO REACTIVO EN VIVO (WEBSOCKETS + UI)
# ==========================================
@st.fragment(run_every=0.8)
def live_dashboard_fragment():
    """Este fragmento se ejecuta automáticamente cada 0.8s, actualiza los datos del WebSocket y redibuja la interfaz en vivo."""

    # 1. Escuchar estado del WebSocket
    fetch_state()  # [Adriana → Josema] movido a una función (ver fetch_state arriba)

    # [Adriana → Josema] Nuevo: barra de estado con lo que están haciendo los agentes ahora mismo,
    # y botón de reintentar si algo falla (p. ej. se agota el cupo de Groq): se reanuda desde
    # el último punto guardado, sin repetir lo que ya estaba hecho.
    s = sess()
    if s.get("phase") == "error":
        st.error(f"⚠️ {s.get('message')}\n\n{s.get('error')}")
        if st.button("🔁 Reintentar", key="btn_retry"):
            send_ws_payload("RETRY", {})
            st.rerun()
    elif s.get("phase") in ("planning", "executing", "finalizing"):
        st.info(f"⏳ {s.get('message')}")

    # 2. Función interna para renderizar cada Hito de forma reactiva
    def render_hito_block(hito_num, hito_title, description):
        st.subheader(f"📌 {hito_title}")
        st.write(description)

        tasks = st.session_state.tasks_state.get(hito_num, [])
        stage = st.session_state.current_stage
        phase = sess().get("phase")
        attempt = attempt_of(hito_num)
        max_attempts = sess().get("max_attempts", 3)

        if stage == hito_num:
            # [Adriana → Josema] Nuevo: el intento actual (el bucle de rehacer tiene un máximo)
            if attempt > 1:
                st.caption(f"Intento {attempt} de {max_attempts}")

            if not tasks:
                st.info("Esperando a que se envíe la petición de investigación para generar las subtareas..."
                        if phase == "idle" else "El agente planificador está proponiendo subtareas…")
                return

            # [Adriana → Josema] Los checkboxes y "Autorizar" solo tienen sentido en la pausa de
            # aprobación; durante la ejecución y la revisión se ocultan para no reenviar la acción.
            if phase == "awaiting_approval":
                st.markdown("**Selecciona las subtareas que deseas autorizar para este hito:**")
                approved_ids = []
                for task in tasks:
                    is_checked = st.checkbox(
                        f"**{task['name']}**",
                        value=(task["status"] != "skipped"),
                        key=f"chk_h{hito_num}_a{attempt}_{task['id']}"  # [Adriana → Josema] + intento: al rehacer, checkboxes nuevos
                    )
                    if is_checked:
                        approved_ids.append(task["id"])

                col_b1, col_b2 = st.columns([1, 4])
                with col_b1:
                    if st.button(f"✅ Autorizar y Ejecutar", key=f"btn_run_{hito_num}_a{attempt}"):
                        if not approved_ids:
                            st.warning("Selecciona al menos una subtarea.")
                        else:
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
                    elif task["status"] == "failed":  # [Adriana → Josema] nuevo estado: la subtarea falló
                        st.error("Falló")
                    elif task["status"] == "pending":  # [Adriana → Josema] nuevo estado: aprobada, en cola
                        st.caption("En cola")

            # [Adriana → Josema] Antes se mostraba cuando todas las barras llegaban al 100%.
            # Ahora se muestra cuando el grafo se detiene en la pausa de revisión: es entonces
            # cuando el resultado está consolidado (p. ej. en el Hito 1 se juntan todas las notas).
            if phase == "awaiting_review":
                st.markdown("---")
                st.markdown(f"### 📋 Resultado Generado por los Agentes (Hito {hito_num})")
                render_result(hito_num)

                # Botones de control: Rehacer hito / Pasar al siguiente
                can_redo = sess().get("can_redo", True)
                col_ctrl1, col_ctrl2 = st.columns(2)
                with col_ctrl1:
                    # [Adriana → Josema] Rehacer ahora lo hace el grafo: vuelve a planificar el hito
                    # usando el comentario. Antes solo se reiniciaban las barras en la pantalla.
                    feedback = st.text_input("¿Qué quieres que cambien los agentes?",
                                             key=f"fb_{hito_num}_a{attempt}", disabled=not can_redo)
                    if st.button(f"🔄 Rehacer Hito {hito_num}", key=f"btn_redo_{hito_num}_a{attempt}",
                                 disabled=not can_redo):
                        send_ws_payload("REVIEW_HITO", {"hito": hito_num, "decision": "redo", "feedback": feedback})
                        st.rerun()
                    if not can_redo:
                        st.caption(f"Límite de {max_attempts} intentos alcanzado: solo se puede aprobar.")
                with col_ctrl2:
                    # [Adriana → Josema] Aprobar se lo dice al grafo (REVIEW_HITO approve), que
                    # planifica el hito siguiente. Antes solo cambiaba current_stage en local.
                    if hito_num < 3:
                        if st.button(f"➡️ Pasar al Siguiente Hito", key=f"btn_next_{hito_num}_a{attempt}"):
                            send_ws_payload("REVIEW_HITO", {"hito": hito_num, "decision": "approve"})
                            st.rerun()
                    else:
                        if st.button(f"🎉 Finalizar Estudio de Mercado", key=f"btn_finish_a{attempt}"):
                            send_ws_payload("REVIEW_HITO", {"hito": hito_num, "decision": "approve"})
                            st.rerun()

        elif stage > hito_num:
            st.success(f"✅ **{hito_title} completado y validado.**")
            # Mostrar también el resultado consolidado del hito ya superado
            with st.expander(f"Ver resultados y subtareas del Hito {hito_num}", expanded=False):
                render_result(hito_num)
        else:
            st.markdown("*Paso bloqueado. Completa los hitos anteriores.*")

        st.markdown("---")

    # Renderizar los 3 Hitos dentro del bucle en vivo
    render_hito_block(1, "Hito 1: Planificación y Aprobación de Subtareas", "El Agente Investigador desglosa la consulta utilizando esquemas tipados.")
    render_hito_block(2, "Hito 2: Validación Cuantitativa (MCP) y Visual", "El Analista de Datos y Especialista Multimodal procesan métricas e imágenes.")
    render_hito_block(3, "Hito 3: Aprobación Final de Informe y Automatización", "El Redactor Estratégico y Revisor Crítico consolidan el entregable final.")

    if st.session_state.current_stage > 3:
        #  Los globos solo una vez por estudio (el fragmento se repite cada 0,8 s)
        if not st.session_state.get("celebrated"):
            st.balloons()
            st.session_state.celebrated = True
        st.success("🏆 **¡Proceso completado de extremo a extremo!** Se han superado los 3 Hitos con éxito.")

        #  La descarga ahora es el informe REAL que exporta el grafo
        # (antes era un Markdown fijo de 3 líneas). Incluye la sección "Supervisión humana".
        final = sess().get("final") or {}
        final_md = final.get("markdown") or f"# Estudio de Mercado: {st.session_state.user_query}\n"

        st.download_button(
            label="📥 Descargar Informe Final (.md)",
            data=final_md,
            file_name="informe_pawtech_market.md",
            mime="text/markdown"
        )
        if final.get("files"):
            st.caption("También guardado en: " + " · ".join(final["files"]))

        if st.button("🔄 Iniciar Nuevo Estudio de Mercado"):
            send_ws_payload("RESET", {})  # [Adriana → Josema] el servidor también empieza de cero
            st.session_state.current_stage = 1
            st.session_state.user_query = ""
            st.session_state.tasks_state = {1: [], 2: [], 3: []}
            st.session_state.celebrated = False
            st.rerun()

# Ejecutar el tablero interactivo en vivo
live_dashboard_fragment()