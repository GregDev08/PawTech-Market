import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    server_path = Path(__file__).resolve().with_name("pawtech_server.py")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Conexion MCP inicializada.")

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print("Herramientas:", tool_names)

            if "analyze_numeric_data" not in tool_names:
                raise RuntimeError("No se encontró analyze_numeric_data.")

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
                raise RuntimeError(f"Error de la herramienta: {result.content}")

            for content in result.content:
                if content.type == "text":
                    print("Resultado del análisis:", content.text)


if __name__ == "__main__":
    asyncio.run(main())
