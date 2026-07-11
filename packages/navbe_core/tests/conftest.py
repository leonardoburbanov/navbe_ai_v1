"""E2E fixtures: isolated NAVBE_HOME, control DB, event bus, mocked httpx."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SAMPLE_TRACES = [
    {
        "id": "trace-acme-1",
        "name": "chat",
        "timestamp": "2026-07-01T10:00:00Z",
        "user_id": "u1",
        "tags": json.dumps(["retailer:acme", "env:test"]),
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "total_cost": 0.01,
        "extras": None,
    },
    {
        "id": "trace-beta-1",
        "name": "chat",
        "timestamp": "2026-07-01T11:00:00Z",
        "user_id": "u2",
        "tags": json.dumps(["retailer:beta"]),
        "prompt_tokens": 20,
        "completion_tokens": 8,
        "total_tokens": 28,
        "total_cost": 0.02,
        "extras": None,
    },
]

TRACE_DETAIL = {
    "id": "trace-acme-1",
    "input": {"prompt": "hello"},
    "output": {"text": "world", "score": 1},
    "metadata": {},
}

API_RESPONSE = {"text": "WORLD", "score": 1}  # differs on text → one diff


@pytest.fixture
def navbe_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the hub at an isolated profile directory."""
    home = tmp_path / "navbe_home"
    home.mkdir()
    (home / "data").mkdir()
    monkeypatch.setenv("NAVBE_HOME", str(home))

    import navbe_core.config as cfg

    monkeypatch.setattr(cfg, "NAVBE_HOME", home)
    monkeypatch.setattr(cfg, "CONTROL_DB", home / "control.db")
    monkeypatch.setattr(cfg, "DATA_DIR", home / "data")
    monkeypatch.setattr(cfg, "DATABASE_URL", f"sqlite:///{home / 'control.db'}")

    import navbe_core.models as models

    engine = create_engine(
        f"sqlite:///{home / 'control.db'}", connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(models, "engine", engine)
    monkeypatch.setattr(models, "SessionLocal", Session)

    import navbe_core.agent as agent_mod

    monkeypatch.setattr(agent_mod, "DATA_DIR", home / "data")
    monkeypatch.setattr(agent_mod, "SessionLocal", Session)

    import navbe_core.secrets as secrets_mod

    monkeypatch.setattr(secrets_mod, "_KEY_PATH", home / "secret.key")

    import navbe_core.query as query_mod

    monkeypatch.setattr(query_mod, "DATA_DIR", home / "data")

    return home


@pytest.fixture
def hub(navbe_home: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Initialized control plane + bus + agent + dispatch helper."""
    import navbe_mcp.tools  # noqa: F401 — register tools
    from navbe_core.agent import WorkflowAgent
    from navbe_core.models import SessionLocal, UserModel, init_db
    from navbe_core.repository import WorkflowRepository
    from navbe_mcp.registry import dispatch
    from navbe_notify import bus
    from navbe_scheduler.scheduler import APSchedulerAdapter

    init_db()
    bus.init(navbe_home / "events.db")

    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.id == "demo").first()
    if user is None:
        user = UserModel(id="demo", email="demo@navbe.local")
        db.add(user)
        db.commit()

    scheduler = APSchedulerAdapter()
    # Don't start AsyncIOScheduler in sync tests — register is a no-op until start.
    monkeypatch.setattr(scheduler, "register", MagicMock())
    monkeypatch.setattr(scheduler, "start", MagicMock())
    monkeypatch.setattr(scheduler, "load_existing", MagicMock())

    repo = WorkflowRepository(db)
    agent = WorkflowAgent(repo, scheduler)

    def run(tool: str, **kwargs: Any) -> dict:
        return dispatch(tool, agent=agent, user_id="demo", **kwargs)

    duck_path = str(navbe_home / "data" / "e2e.duckdb")

    # Patch Langfuse extract used by export graph
    monkeypatch.setattr(
        "navbe_core.steps.fetch_last_traces",
        lambda *a, **k: list(SAMPLE_TRACES),
    )

    # Patch httpx for fetch_trace + call_api (imported inside step bodies)
    import httpx

    def fake_get(url: str, *args: Any, **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "/api/public/traces/" in url:
            resp.json.return_value = dict(TRACE_DETAIL)
        else:
            resp.json.return_value = {"data": [], "meta": {}}
        return resp

    def fake_request(method: str, url: str, *args: Any, **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = dict(API_RESPONSE)
        resp.text = json.dumps(API_RESPONSE)
        return resp

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "request", fake_request)

    try:
        yield {
            "home": navbe_home,
            "db": db,
            "agent": agent,
            "repo": repo,
            "run": run,
            "duck_path": duck_path,
            "bus": bus,
        }
    finally:
        db.close()
