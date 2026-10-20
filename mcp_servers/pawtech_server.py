from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PawTech Market Tools")


@mcp.tool()
def server_status() -> dict[str, str]:
    """Comprueba que el servidor de herramientas de PawTech responde."""
    return {
        "status": "ok",
        "server": "pawtech-market-tools",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")