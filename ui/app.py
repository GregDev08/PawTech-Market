import streamlit as st
from streamlit_option_menu import option_menu
from pages import dashboard, approval

# Configuración de la página
st.set_page_config(
    page_title="PawTech-Market | AgentSquad",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto"
)

# Inicializar el estado global compartido para la sincronización de agentes
if 'agent_data' not in st.session_state:
    st.session_state.agent_data = []

# Menú de navegación superior
selected = option_menu(
    menu_title="PawTech-Market | Sistema Multi-Agente",
    options=["Dashboard", "Approval"],
    icons=["graph-up-arrow", "check2-circle"],
    menu_icon="cpu",
    default_index=0,
    orientation="horizontal"
)

# Enrutamiento de páginas
if selected == "Dashboard":
    dashboard.show()
elif selected == "Approval":
    approval.show()