import json
import os
from pathlib import Path
from typing import Any, List, Optional

import yaml
from crewai import Agent
from crewai.tools import tool
from dotenv import load_dotenv

# Cargar las variables del archivo .env
load_dotenv()

# Importar la función de análisis cuantitativo
from tools.python_analysis import analyze_numeric_data as run_numeric_analysis

# Cargar la configuración de los agentes desde YAML
CONFIG_PATH = Path(__file__).resolve().parent / "config" / "agents.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    agents_config = yaml.safe_load(f)


# Herramienta nativa de CrewAI con manejo robusto de cadenas JSON
@tool("Analizador de Datos Numéricos PawTech")
def analyze_numeric_data_tool(rows_json: str) -> str:
    """Calcula estadísticas descriptivas de datos numéricos (ventas, precios, unidades) recibidos en formato de cadena JSON.

    Ejemplo: '[{"precio": 10.5, "unidades": 100}]'
    """
    try:
        if isinstance(rows_json, str):
            rows = json.loads(rows_json)
        else:
            rows = rows_json

        result = run_numeric_analysis(rows)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": f"Error al procesar los datos numéricos: {str(e)}"},
            ensure_ascii=False,
        )


# Definición de Agentes
def get_market_researcher(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["market_researcher"]["role"],
        goal=agents_config["market_researcher"]["goal"],
        backstory=agents_config["market_researcher"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=True,
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
        allow_delegation=True,
    )


def get_visual_analyst(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["visual_analyst"]["role"],
        goal=agents_config["visual_analyst"]["goal"],
        backstory=agents_config["visual_analyst"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=True,
    )


def get_strategic_writer(tools: Optional[List[Any]] = None) -> Agent:
    assigned_tools = tools if tools is not None else []
    return Agent(
        role=agents_config["strategic_writer"]["role"],
        goal=agents_config["strategic_writer"]["goal"],
        backstory=agents_config["strategic_writer"]["backstory"],
        tools=assigned_tools,
        verbose=True,
        allow_delegation=True,
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
    )