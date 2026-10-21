import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Permite importar el paquete "tools" desde la raíz del proyecto
# aunque este servidor se ejecute directamente por su ruta.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.python_analysis import (
    analyze_numeric_data as run_numeric_analysis,
)

mcp = FastMCP("PawTech Market Tools")


@mcp.tool()
def server_status() -> dict[str, str]:
    """Comprueba que el servidor de herramientas de PawTech responde."""
    return {
        "status": "ok",
        "server": "pawtech-market-tools",
    }


@mcp.tool()
def analyze_numeric_data(rows: list[dict[str, float]]) -> dict[str, Any]:
    """Calcula estadísticas descriptivas de filas con datos numéricos."""
    return run_numeric_analysis(rows)


if __name__ == "__main__":
    mcp.run(transport="stdio")
