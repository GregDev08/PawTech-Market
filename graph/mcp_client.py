"""Cliente MCP del Hito 2: aquí conecto el grafo con la herramienta de Luis.

Luis expuso `analyze_numeric_data` en su servidor MCP (mcp_servers/pawtech_server.py).
Yo arranco ese servidor como un proceso aparte, le hablo por stdio con el protocolo
MCP, le paso las filas de precios €/kg y me devuelve las estadísticas.

Si por lo que sea el servidor no arranca (en el portátil de alguien, en una demo…),
no quiero que se caiga el estudio entero: uso la misma función de Luis en local y
dejo anotado en el resultado por qué vía se calculó ("mcp" o "python_local").
"""
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

# Ruta al servidor de Luis, calculada desde la raíz del proyecto
SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp_servers" / "pawtech_server.py"


def _clean(value: Any) -> Any:
    """Cambio NaN/infinito por None: pandas los genera (p. ej. la desviación con 1 solo
    precio) y rompen el JSON que luego viaja a la interfaz."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


async def _call_mcp(rows: list[dict[str, float]]) -> dict[str, Any]:
    """Hablo con el servidor MCP de Luis: lo arranco, abro sesión y llamo a su herramienta."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Lanzo el servidor con el mismo Python que estoy usando yo (mismo entorno, mismas librerías)
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("analyze_numeric_data", arguments={"rows": rows})
            if result.isError:
                raise RuntimeError(f"Error de la herramienta MCP: {result.content}")
            # Según la versión de MCP, la respuesta llega como datos estructurados o como texto JSON
            if result.structuredContent:
                data = result.structuredContent
                return data.get("result", data) if isinstance(data, dict) else data
            for content in result.content:
                if content.type == "text":
                    return json.loads(content.text)
            raise RuntimeError("La herramienta MCP no devolvió contenido.")


def analyze_numeric_data(rows: list[dict[str, float]]) -> dict[str, Any]:
    """Estadísticas descriptivas de las filas: por MCP y, si falla, en local.

    Esta es la única función que usa el grafo. Es síncrona a propósito, porque los
    nodos de LangGraph y CrewAI que uso también lo son.
    """
    try:
        # 30 s de margen: arrancar el servidor la primera vez tarda un poco
        stats = asyncio.run(asyncio.wait_for(_call_mcp(rows), timeout=30))
        via = "mcp"
    except Exception as exc:  # cualquier fallo del servidor: no paro el estudio
        from tools.python_analysis import analyze_numeric_data as local

        stats = local(rows)
        via = f"python_local (MCP no disponible: {exc.__class__.__name__})"
    return {"via": via, **_clean(stats)}