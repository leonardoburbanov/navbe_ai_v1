# Sprint 0 — Monorepo Scaffold

Mechanical work: move existing `navbe_ai_orchestrator_backend` into the monorepo layout and wire quality tooling. No new business logic.

## Goal

`uv sync` at root installs everything. `navbe version` runs. `make check` passes on empty stubs.

## Repo layout to create

```
navbe_ai_v1/
  pyproject.toml              # uv workspace root
  Makefile                    # check / lint / typecheck / test targets
  packages/
    navbe_core/
      pyproject.toml
      navbe_core/
        __init__.py
        models.py             # lifted from orchestrator_backend/models.py
        repository.py         # lifted from orchestrator_backend/repository.py
        graph.py              # lifted from orchestrator_backend/graph.py
        steps.py              # lifted from orchestrator_backend/steps.py
        agent.py              # lifted from orchestrator_backend/agent.py
        config.py             # adapted: profile home = ~/.navbe
        secrets.py            # Fernet key at ~/.navbe/secret.key
    navbe_mcp/
      pyproject.toml
      navbe_mcp/
        __init__.py
        registry.py           # lifted from tools/registry.py
        tools/                # lifted from tools/*.py (connectors, destinations, runs, etc.)
    navbe_api/
      pyproject.toml
      navbe_api/
        __init__.py
        app.py                # FastAPI app + lifespan (from main.py)
        sse.py                # SSE /events/sse endpoint
    navbe_scheduler/
      pyproject.toml
      navbe_scheduler/
        __init__.py
        scheduler.py          # lifted from orchestrator_backend/scheduler.py
    navbe_notify/
      pyproject.toml
      navbe_notify/
        __init__.py
        bus.py                # stub — upgrade in Sprint 1
    navbe_connectors/
      pyproject.toml
      navbe_connectors/
        __init__.py
        langfuse.py           # lifted from orchestrator_backend/connectors.py
    navbe_destinations/
      pyproject.toml
      navbe_destinations/
        __init__.py
        duckdb.py             # lifted from orchestrator_backend/exports.py
    navbe_transforms/
      pyproject.toml
      navbe_transforms/
        __init__.py
        tags.py               # stub — retailer tag parse in Sprint 2
  apps/
    cli/
      pyproject.toml
      navbe_cli/
        __init__.py
        main.py               # Typer: navbe daemon | navbe version
    web/
      package.json            # pnpm, Vite+React+TS stub
      biome.json
      tsconfig.json
      src/
        main.tsx
        App.tsx
```

## Root pyproject.toml

```toml
[tool.uv.workspace]
members = ["packages/*", "apps/cli"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TCH"]

[tool.ty]
python-version = "3.12"

[tool.pytest.ini_options]
testpaths = ["packages"]
addopts = "-q --tb=short"
```

## Each package pyproject.toml pattern

```toml
[project]
name = "navbe-core"           # use package name
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
    # add specific deps per package
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Makefile targets

```makefile
.PHONY: check lint typecheck test fmt

fmt:
	uv run ruff format packages/ apps/cli/

lint:
	uv run ruff check packages/ apps/cli/
	uv run ruff format --check packages/ apps/cli/

typecheck:
	uv run ty check packages/ apps/cli/

test:
	uv run pytest packages/

check: lint typecheck test
	@echo "All checks passed"
```

## Config adaptation

`navbe_core/config.py` — replace the orchestrator's `DATABASE_URL` / `EXPORTS_DIR` env vars with a profile-home approach:

```python
from pathlib import Path
import os

NAVBE_HOME = Path(os.environ.get("NAVBE_HOME", Path.home() / ".navbe"))
NAVBE_HOME.mkdir(parents=True, exist_ok=True)

CONTROL_DB = NAVBE_HOME / "control.db"
DATA_DIR = NAVBE_HOME / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{CONTROL_DB}"
```

Add `schema_version` table to `init_db()`:

```python
con.execute("""
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
""")
```

## CLI entry (apps/cli)

```python
import typer
import uvicorn

app = typer.Typer()

@app.command()
def daemon(port: int = 7700, host: str = "127.0.0.1"):
    """Start the Navbe daemon (MCP + REST + SSE)."""
    from navbe_api.app import create_app
    uvicorn.run(create_app(), host=host, port=port)

@app.command()
def version():
    """Print Navbe version."""
    typer.echo("navbe 0.1.0")
```

## Import fix pattern

All lifted files: replace `from config import` → `from navbe_core.config import`, `from models import` → `from navbe_core.models import`, etc.

## MCP wiring (in CLI help)

Add to `daemon` docstring: "Connect Cursor at http://<host>:<port>/mcp (streamable HTTP transport)."

## apps/web stub

```json
{
  "name": "navbe-web",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "check": "tsc --noEmit && pnpm biome ci src/",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^19",
    "react-dom": "^19"
  },
  "devDependencies": {
    "@biomejs/biome": "latest",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "typescript": "^5",
    "vite": "^6",
    "@vitejs/plugin-react": "^4",
    "vitest": "^2"
  }
}
```

## Done when

- `uv sync` at root succeeds
- `navbe version` prints version
- `navbe daemon` starts on port 7700 (same MCP tools as orchestrator_backend)
- `make check` passes (ruff + ty + pytest with no test files = passes vacuously)
