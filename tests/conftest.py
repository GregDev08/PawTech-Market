"""Configuración común de los tests de la orquestación (graph/).

Todos los tests del grafo corren en modo simulado (FAKE_LLM=1): no llaman a Groq,
no gastan tokens y no necesitan .env. Así cualquiera del equipo puede lanzar
`pytest` en su ordenador o en CI y comprobar que el flujo sigue funcionando.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    """Activo el modo simulado sin esperas y mando los informes a una carpeta temporal.

    - FAKE_LLM=1: el runner devuelve respuestas de graph/fake_llm.py.
    - DELAY=0: los "pasos" simulados no esperan (los tests van rápidos).
    - OUTPUT_DIR temporal: los tests no ensucian la carpeta outputs/ del proyecto.
    - MCP en local: no arranco el servidor de Luis en cada test (lo pruebo aparte).
    """
    from graph import fake_llm as fake, mcp_client, workflow
    from tools.python_analysis import analyze_numeric_data

    monkeypatch.setenv("FAKE_LLM", "1")
    monkeypatch.setattr(fake, "DELAY", 0)
    monkeypatch.setattr(workflow, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(mcp_client, "analyze_numeric_data",
                        lambda rows: {"via": "test", **analyze_numeric_data(rows)})
    return tmp_path
