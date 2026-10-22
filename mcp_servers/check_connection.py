import asyncio
import json
import math
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError


# Añadimos la raíz del proyecto para importar el esquema Pydantic.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.python_analysis import NumericAnalysisResult


def extract_response(result):
    """Extrae la respuesta tanto si MCP devuelve datos estructurados
    como si devuelve un texto que contiene JSON.
    """

    if result.structuredContent:
        data = result.structuredContent

        if isinstance(data, dict):
            return data.get("result", data)

        return data

    for content in result.content:
        if content.type == "text":
            try:
                return json.loads(content.text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "La herramienta ha devuelto texto que no es JSON válido."
                ) from exc

    raise RuntimeError(
        "La herramienta MCP no ha devuelto contenido válido."
    )


def check_expected_values(response: NumericAnalysisResult) -> None:
    """Comprueba que el análisis devuelve los valores esperados."""

    if response.row_count != 3:
        raise RuntimeError(
            f"row_count incorrecto: {response.row_count}; se esperaba 3."
        )

    if response.columns != ["ventas"]:
        raise RuntimeError(
            f"Columnas incorrectas: {response.columns}; "
            "se esperaba ['ventas']."
        )

    statistics = response.summary["ventas"]

    expected_values = {
        "count": 3,
        "mean": 20,
        "std": 10,
        "min": 10,
        "25%": 15,
        "50%": 20,
        "75%": 25,
        "max": 30,
    }

    for metric, expected in expected_values.items():
        actual = statistics[metric]

        if actual is None or not math.isclose(
            actual,
            expected,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise RuntimeError(
                f"Valor incorrecto para '{metric}': "
                f"{actual}; se esperaba {expected}."
            )


async def main() -> None:
    server_path = Path(__file__).resolve().with_name(
        "pawtech_server.py"
    )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Conexión MCP inicializada.")

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]

            print("Herramientas:", tool_names)

            if "analyze_numeric_data" not in tool_names:
                raise RuntimeError(
                    "No se encontró analyze_numeric_data."
                )

            result = await session.call_tool(
                "analyze_numeric_data",
                arguments={
                    "rows": [
                        {"ventas": 10},
                        {"ventas": 20},
                        {"ventas": 30},
                    ]
                },
            )

            if result.isError:
                raise RuntimeError(
                    f"Error de la herramienta MCP: {result.content}"
                )

            raw_response = extract_response(result)

            # Validación de la estructura devuelta por MCP.
            try:
                response = NumericAnalysisResult.model_validate(
                    raw_response
                )
            except ValidationError as exc:
                raise RuntimeError(
                    "La respuesta MCP no cumple el esquema esperado."
                ) from exc

            # Validación de los resultados calculados.
            check_expected_values(response)

            print(
                "Resultado del análisis:",
                response.model_dump_json(indent=2),
            )

            print(
                "Validación completada: "
                "estructura y valores esperados correctos."
            )


if __name__ == "__main__":
    asyncio.run(main())