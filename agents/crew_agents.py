import os
import yaml
from pathlib import Path
from typing import Optional, List, Any
from dotenv import load_dotenv
from crewai import Agent
from crewai.tools import tool

# Cargar las variables del archivo .env
load_dotenv()

# Importar la función creada por la Persona 3 (MCP Lead)
from tools.python_analysis import analyze_numeric_data as run_numeric_analysis

# Cargar la configuración de los agentes desde YAML
CONFIG_PATH = Path(__file__).resolve().parent / "config" / "agents.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    agents_config = yaml.safe_load(f)

# Wrapper de la herramienta Python / MCP con el decorador nativo de CrewAI
@tool("Analizador de Datos Numéricos PawTech")
def analyze_numeric_data_tool(rows: list[dict[str, float]]) -> dict:
    """Calcula estadísticas descriptivas de listas con datos numéricos (ventas, precios, unidades)."""
    return run_numeric_analysis(rows)


def get_market_researcher(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["market_researcher"]["role"],
        goal=agents_config["market_researcher"]["goal"],
        backstory=agents_config["market_researcher"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=True,
        llm="gpt-4o-mini"
    )

def get_data_analyst(extra_tools: Optional[List[Any]] = None) -> Agent:
    """Asigna automáticamente la herramienta de análisis cuantitativo al Analista de Datos."""
    assigned_tools = [analyze_numeric_data_tool]
    if extra_tools:
        assigned_tools.extend(extra_tools)
        
    return Agent(
        role=agents_config["data_analyst"]["role"],
        goal=agents_config["data_analyst"]["goal"],
        backstory=agents_config["data_analyst"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=False,
        llm="gpt-4o-mini"
    )

def get_visual_analyst(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["visual_analyst"]["role"],
        goal=agents_config["visual_analyst"]["goal"],
        backstory=agents_config["visual_analyst"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=False,
        llm="gpt-4o"  # Visión multimodal habilitada
    )

def get_strategic_writer(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["strategic_writer"]["role"],
        goal=agents_config["strategic_writer"]["goal"],
        backstory=agents_config["strategic_writer"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=False,
        llm="gpt-4o-mini"
    )

def get_critical_reviewer(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["critical_reviewer"]["role"],
        goal=agents_config["critical_reviewer"]["goal"],
        backstory=agents_config["critical_reviewer"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=True,
        llm="gpt-4o-mini"
    )