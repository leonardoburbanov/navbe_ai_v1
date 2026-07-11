---
name: navbe-scaffold
description: Implements Sprint 0 of the Navbe monorepo harness — uv workspace layout, lifting orchestrator_backend files into packages, Typer CLI, profile-home config, and quality tooling (ruff, ty, pytest, Biome). Use when bootstrapping the navbe_ai_v1 repo structure or setting up any package in the monorepo.
---

# Navbe Scaffold — Sprint 0

Full spec: [.cursor/plans/sprint0-scaffold.md](.cursor/plans/sprint0-scaffold.md)

## Rules (always apply)

- Python 3.12+, `uv` for all Python deps, `pnpm` for frontend.
- Pydantic v2 for every public API boundary (MCP tool I/O, REST bodies, config).
- `ty` for type checking (not mypy), `ruff` for lint+format (not black/flake8).
- Profile home: `~/.navbe/` on Linux/Mac, `%USERPROFILE%\.navbe\` on Windows. Never hard-code paths.
- Import rule: apps → packages; packages never import from apps; no circular imports.
- All lifted files keep `ponytail:` comments from the original — do not delete them.

## Package layout

Each package under `packages/` follows this structure:

```
navbe_<name>/
  pyproject.toml
  navbe_<name>/
    __init__.py
    ...
```

Each `pyproject.toml` must include:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Lift checklist

When moving a file from `navbe_ai_orchestrator_backend/` to a package:

1. Fix all intra-package imports (`from config import` → `from navbe_core.config import`).
2. Keep the file's docstrings and `ponytail:` comments verbatim.
3. Do not add new business logic — lift exactly, then the sprint plan adds the delta.

## Config (navbe_core/config.py)

```python
from pathlib import Path
import os

NAVBE_HOME = Path(os.environ.get("NAVBE_HOME", Path.home() / ".navbe"))
NAVBE_HOME.mkdir(parents=True, exist_ok=True)
CONTROL_DB = NAVBE_HOME / "control.db"
DATA_DIR   = NAVBE_HOME / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{CONTROL_DB}"
```

## Quality commands

```bash
make lint        # ruff check + ruff format --check
make typecheck   # uv run ty check packages/ apps/cli/
make test        # uv run pytest packages/
make check       # all three
```

Frontend (apps/web):
```bash
pnpm check       # tsc --noEmit && biome ci src/
pnpm test        # vitest run
```

## Done signal

`navbe version` prints version. `navbe daemon` starts on port 7700 with same MCP tools as orchestrator_backend. `make check` exits 0.
