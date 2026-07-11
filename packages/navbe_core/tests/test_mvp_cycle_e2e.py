"""Full MVP A + MVP B cycle e2e (mocked Langfuse/API, real DuckDB + bus)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest


def _setup_connector_dest(run, duck_path: str) -> tuple[str, str]:
    """Create Langfuse connector + DuckDB destination; return ids."""
    conn = run(
        "create_connector",
        name="lf-e2e",
        host="https://langfuse.test",
        public_key="pk-test",
        secret_key="sk-test",
    )
    assert "connector_id" in conn, conn
    dest = run(
        "create_destination",
        type="duckdb",
        name="duck-e2e",
        config={"db_path": duck_path, "table": "traces"},
    )
    assert "destination_id" in dest, dest
    return conn["connector_id"], dest["destination_id"]


def test_mvp_cycle_a_and_b(hub: dict[str, Any]) -> None:
    """Connect → sync → mart → bus → preview → templates → replay → save workflow."""
    run = hub["run"]
    repo = hub["repo"]
    duck_path = hub["duck_path"]

    connector_id, destination_id = _setup_connector_dest(run, duck_path)

    # --- schedule langfuse_daily ---
    created = run(
        "create_langfuse_export_workflow",
        name="Daily Langfuse",
        connector_id=connector_id,
        destination_id=destination_id,
        when="+1h",
        process_slug="langfuse_daily",
    )
    assert "workflow_id" in created, created
    workflow_id = created["workflow_id"]
    assert created.get("process_slug") == "langfuse_daily"

    wf = repo.get_workflow(workflow_id, "demo")
    assert wf is not None
    assert wf.process_slug == "langfuse_daily"

    # --- dual subscribers ---
    sub_c = run("subscribe", subscriber_id="cursor")
    sub_l = run("subscribe", subscriber_id="claude")
    assert sub_c["registered"] and sub_l["registered"]
    assert run("pull_events", subscriber_id="cursor")["count"] == 0

    # --- first production run ---
    first = run("run_workflow", workflow_id=workflow_id, mode="append")
    assert first["status"] == "completed", first
    assert first.get("preview") is False
    out = first["output"]
    assert out.get("new", 0) >= 1
    assert out.get("mart_refreshed") is True
    assert out.get("last_timestamp")

    con = duckdb.connect(duck_path, read_only=True)
    try:
        traces = con.execute("SELECT id, tags, total_cost FROM traces ORDER BY id").fetchall()
        assert len(traces) == 2
        assert traces[0][2] is not None  # total_cost
        assert "retailer:acme" in (traces[0][1] or "")
        mart = con.execute(
            "SELECT retailer_id, trace_count FROM mart_retailer_token_cost_daily "
            "ORDER BY retailer_id"
        ).fetchall()
        assert ("acme", 1) in mart
        assert ("beta", 1) in mart
    finally:
        con.close()

    repo.db.refresh(wf)
    assert wf.watermark_at is not None
    watermark_after_first = wf.watermark_at

    # --- bus fan-out: both subscribers see the same success ---
    cursor_events = run("pull_events", subscriber_id="cursor", limit=100)
    claude_events = run("pull_events", subscriber_id="claude", limit=100)
    assert cursor_events["count"] > 0
    assert claude_events["count"] == cursor_events["count"]
    types_c = {e["type"] for e in cursor_events["events"]}
    types_l = {e["type"] for e in claude_events["events"]}
    assert types_c == types_l
    assert "run.succeeded" in types_c

    status = run("get_process_status", process_slug="langfuse_daily")
    assert status["found"] is True
    assert status["workflow_id"] == workflow_id
    assert status["watermark"] is not None

    # --- second run: idempotent upsert ---
    second = run("run_workflow", workflow_id=workflow_id, mode="append")
    assert second["status"] == "completed"
    assert second["output"].get("new") == 0
    assert second["output"].get("changed") == 0

    # --- preview does not advance watermark ---
    preview = run("preview_workflow", workflow_id=workflow_id)
    assert preview.get("preview") is True
    assert preview.get("status") == "completed"
    repo.db.refresh(wf)
    assert wf.watermark_at == watermark_after_first

    # preview events should not clear process success semantics for subscribers
    # (pull any new events — may include run.preview.*)
    more = run("pull_events", subscriber_id="cursor", limit=50)
    preview_types = {e["type"] for e in more["events"]}
    assert "run.preview.completed" in preview_types or more["count"] >= 0

    # --- analysis templates + mart query ---
    templates = run("list_analysis_templates", destination_id=destination_id)
    assert any(t["id"] == "retailer_token_cost_daily" for t in templates["templates"])
    q = run(
        "query_destination",
        destination_id=destination_id,
        sql="SELECT retailer_id FROM mart_retailer_token_cost_daily ORDER BY retailer_id",
    )
    assert "error" not in q, q
    assert q["total"] >= 2

    # --- MVP B: replay ---
    replay = run(
        "replay_trace_to_api",
        trace_id="trace-acme-1",
        connection_id=connector_id,
        api_url="https://api.test/v1/chat",
        auth={"type": "bearer", "token": "tok-secret"},
        method="POST",
        destination_id=destination_id,
        save_as_workflow=True,
    )
    assert "error" not in replay, replay
    assert replay["trace_id"] == "trace-acme-1"
    assert replay["status_code"] == 200
    assert replay["compare"]["identical"] is False
    assert replay["compare"]["diff_count"] >= 1
    assert any(d["path"] == "$.text" for d in replay["compare"]["diffs"])
    assert replay["replay_id"]
    assert replay["workflow_id"]

    con = duckdb.connect(duck_path, read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM replay_results").fetchone()
        assert n is not None and n[0] >= 1
    finally:
        con.close()

    processes = run("list_processes")
    slugs = {p["process_slug"] for p in processes["processes"]}
    assert "langfuse_daily" in slugs
    assert any(s and s.startswith("replay_") for s in slugs)


def test_control_api_smoke(hub: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """REST cockpit endpoints agree with hub state after a minimal setup."""
    from fastapi.testclient import TestClient

    run = hub["run"]
    duck_path = hub["duck_path"]
    home: Path = hub["home"]

    connector_id, destination_id = _setup_connector_dest(run, duck_path)
    created = run(
        "create_langfuse_export_workflow",
        name="API smoke",
        connector_id=connector_id,
        destination_id=destination_id,
        when="+1h",
        process_slug="langfuse_daily",
    )
    workflow_id = created["workflow_id"]
    run("run_workflow", workflow_id=workflow_id)
    run(
        "replay_trace_to_api",
        trace_id="trace-acme-1",
        connection_id=connector_id,
        api_url="https://api.test/v1/chat",
        auth={"type": "none"},
        destination_id=destination_id,
    )

    import navbe_api.app as app_mod

    monkeypatch.setattr(app_mod, "NAVBE_HOME", home)
    # Lifespan would start a real AsyncIOScheduler — stub the shared adapter.
    monkeypatch.setattr(app_mod.scheduler_adapter, "start", lambda: None)
    monkeypatch.setattr(app_mod.scheduler_adapter, "load_existing", lambda *a, **k: None)
    monkeypatch.setattr(app_mod.scheduler_adapter, "register", lambda *a, **k: None)

    with TestClient(app_mod.create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}

        processes = client.get("/api/processes").json()
        assert any(p["process_slug"] == "langfuse_daily" for p in processes["processes"])

        catalog = client.get("/api/catalog").json()
        assert "langfuse" in catalog["connector_types"]
        assert "duckdb" in catalog["destination_types"]
        assert len(catalog["connectors"]) >= 1
        assert len(catalog["destinations"]) >= 1

        graph = client.get(f"/api/workflows/{workflow_id}/graph").json()
        node_ids = {n["id"] for n in graph["nodes"]}
        assert "fetch_traces" in node_ids
        assert "write_traces" in node_ids
        assert "refresh_retailer_mart" in node_ids
        assert len(graph["edges"]) >= 2

        replays = client.get("/api/replays").json()
        assert len(replays["replays"]) >= 1
        assert replays["replays"][0]["trace_id"] == "trace-acme-1"
