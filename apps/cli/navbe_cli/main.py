"""Navbe CLI — daemon and version commands.

Connect Cursor at http://<host>:<port>/mcp (streamable HTTP transport).
"""

from __future__ import annotations

import typer
import uvicorn

app = typer.Typer(name="navbe", help="Navbe — workflow automation hub for AI agents.")


@app.command()
def daemon(port: int = 7700, host: str = "127.0.0.1") -> None:
    """Start the Navbe daemon (MCP + REST + SSE).

    Connect Cursor at http://<host>:<port>/mcp (streamable HTTP transport).
    """
    from navbe_api.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def version() -> None:
    """Print Navbe version."""
    typer.echo("navbe 0.1.0")


if __name__ == "__main__":
    app()
