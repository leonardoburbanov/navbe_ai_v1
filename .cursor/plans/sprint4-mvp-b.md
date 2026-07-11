# Sprint 4 — MVP B: Trace Replay → API → Compare

Single MCP tool `replay_trace_to_api`. Fetches Langfuse trace I/O, calls a user-defined API with auth, stores request+response, returns a structured diff. Optionally saves as a reusable workflow.

---

## Pydantic models (navbe_core/models_replay.py)

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, HttpUrl


class AuthConfig(BaseModel):
    type: Literal["none", "bearer", "api_key", "basic"]
    token: str | None = None        # bearer / api_key value — encrypt before storing
    header: str = "Authorization"   # override for api_key (e.g. "X-API-Key")
    username: str | None = None     # basic auth
    password: str | None = None     # basic auth — encrypt before storing


class ReplayRequest(BaseModel):
    trace_id: str
    connection_id: str              # existing Langfuse connection id
    api_url: str
    method: Literal["GET", "POST", "PUT", "PATCH"] = "POST"
    auth: AuthConfig
    input_mapping: dict = {}        # optional: remap trace input keys to request body keys
    destination_id: str | None = None
    save_as_workflow: bool = False


class DiffEntry(BaseModel):
    path: str                       # JSON path, e.g. "$.choices[0].message.content"
    expected: object
    actual: object
    match: bool


class CompareResult(BaseModel):
    identical: bool
    diff_count: int
    diffs: list[DiffEntry]


class ReplayResult(BaseModel):
    replay_id: str
    trace_id: str
    status_code: int
    latency_ms: float
    compare: CompareResult
    workflow_id: str | None = None  # set if save_as_workflow=True
    next_step: str
```

---

## LangGraph steps (navbe_core/steps.py additions)

### fetch_trace

```python
@step("fetch_trace", retries=2)
def fetch_trace(state: dict) -> dict:
    """Fetch a single trace by ID from Langfuse including input/output."""
    import httpx
    host, pub, sec = state["host"], state["public_key"], state["secret_key"]
    r = httpx.get(
        f"{host.rstrip('/')}/api/public/traces/{state['trace_id']}",
        auth=(pub, sec), timeout=30
    )
    r.raise_for_status()
    data = r.json()
    return {
        "trace_input": data.get("input"),
        "trace_output": data.get("output"),
        "trace_metadata": data.get("metadata", {}),
    }
```

### call_api

```python
@step("call_api", retries=1)
def call_api(state: dict) -> dict:
    """Call the target API with the mapped request body and auth."""
    import httpx, time, json as _json

    auth_cfg = state["auth"]                    # AuthConfig dict
    mapping = state.get("input_mapping", {})
    body = dict(state["trace_input"] or {})

    # apply key remapping
    for src, dst in mapping.items():
        if src in body:
            body[dst] = body.pop(src)

    headers = {}
    auth = None
    if auth_cfg["type"] == "bearer":
        headers["Authorization"] = f"Bearer {auth_cfg['token']}"
    elif auth_cfg["type"] == "api_key":
        headers[auth_cfg.get("header", "Authorization")] = auth_cfg["token"]
    elif auth_cfg["type"] == "basic":
        auth = (auth_cfg["username"], auth_cfg["password"])

    t0 = time.perf_counter()
    r = httpx.request(
        state["method"], state["api_url"],
        json=body, headers=headers, auth=auth, timeout=60,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    response_body = None
    try:
        response_body = r.json()
    except Exception:
        response_body = {"_raw": r.text}

    return {
        "api_status_code": r.status_code,
        "api_response": response_body,
        "api_latency_ms": latency_ms,
        "api_request_body": body,
    }
```

### compare_outputs

```python
@step("compare_outputs")
def compare_outputs(state: dict) -> dict:
    """Structured JSON diff: trace output vs API response."""
    original = state.get("trace_output") or {}
    actual = state.get("api_response") or {}
    diffs = _diff(original, actual, "$")
    result = {
        "identical": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs,
    }
    return {"compare_result": result}


def _diff(expected: object, actual: object, path: str) -> list[dict]:
    """Recursive JSON diff. Returns list of {path, expected, actual, match}."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        all_keys = expected.keys() | actual.keys()
        for k in all_keys:
            out.extend(_diff(expected.get(k), actual.get(k), f"{path}.{k}"))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        out = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            out.extend(_diff(e, a, f"{path}[{i}]"))
        if len(expected) != len(actual):
            out.append({"path": f"{path}.length", "expected": len(expected),
                        "actual": len(actual), "match": False})
        return out
    match = expected == actual
    if not match:
        return [{"path": path, "expected": expected, "actual": actual, "match": False}]
    return []
```

### store_replay

```python
@step("store_replay")
def store_replay(state: dict) -> dict:
    """Upsert replay result row into DuckDB replay_results table."""
    import duckdb, json as _json, uuid
    from datetime import datetime, UTC

    if not state.get("dest_config"):
        return {"replay_id": None}   # no destination configured — skip persist

    db_path = state["dest_config"]["db_path"]
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS replay_results (
            id VARCHAR PRIMARY KEY,
            trace_id VARCHAR NOT NULL,
            api_url VARCHAR NOT NULL,
            request_body JSON,
            response_body JSON,
            status_code INTEGER,
            latency_ms DOUBLE,
            original_output JSON,
            diff_summary JSON,
            ts TIMESTAMPTZ NOT NULL,
            extras JSON
        )
    """)
    replay_id = str(uuid.uuid4())
    con.execute(
        "INSERT INTO replay_results VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            replay_id, state["trace_id"], state["api_url"],
            _json.dumps(state.get("api_request_body")),
            _json.dumps(state.get("api_response")),
            state.get("api_status_code"),
            state.get("api_latency_ms"),
            _json.dumps(state.get("trace_output")),
            _json.dumps(state.get("compare_result")),
            datetime.now(UTC).isoformat(),
            None,
        ),
    )
    con.close()
    return {"replay_id": replay_id}
```

---

## MCP tool: replay_trace_to_api (navbe_mcp/tools/replay.py)

```python
from navbe_mcp.registry import register
from navbe_core.models_replay import ReplayRequest, ReplayResult
from navbe_core.graph import build_graph

REPLAY_GRAPH = {
    "entry": "fetch_trace",
    "nodes": ["fetch_trace", "call_api", "compare_outputs", "store_replay"],
    "edges": [
        ["fetch_trace", "call_api"],
        ["call_api", "compare_outputs"],
        ["compare_outputs", "store_replay"],
    ],
}

def _replay_trace_to_api(agent, user_id: str, **kwargs) -> dict:
    req = ReplayRequest(**kwargs)

    connector = agent.repo.get_connector(req.connection_id, user_id)
    if connector is None:
        return {"error": f"Connection not found: {req.connection_id}", "next_step": "call list_connectors"}

    dest_config = None
    if req.destination_id:
        dest = agent.repo.get_destination(req.destination_id, user_id)
        if dest:
            import json
            dest_config = json.loads(dest.config)

    initial = {
        "trace_id": req.trace_id,
        "host": connector.host,
        "public_key": connector.public_key,
        "secret_key": connector.secret_key,
        "api_url": req.api_url,
        "method": req.method,
        "auth": req.auth.model_dump(),
        "input_mapping": req.input_mapping,
        "dest_config": dest_config,
    }

    compiled = build_graph(REPLAY_GRAPH)
    state = dict(initial)
    for update in compiled.stream(state, stream_mode="updates"):
        for _, step_state in update.items():
            state = step_state

    workflow_id = None
    if req.save_as_workflow:
        workflow_id = _save_replay_workflow(agent, user_id, req, initial)

    result = ReplayResult(
        replay_id=state.get("replay_id", ""),
        trace_id=req.trace_id,
        status_code=state.get("api_status_code", 0),
        latency_ms=state.get("api_latency_ms", 0.0),
        compare=state["compare_result"],
        workflow_id=workflow_id,
        next_step="call list_runs or check UI Replays page for stored results" if req.destination_id
                  else "pass destination_id to persist results",
    )
    return result.model_dump()


def _save_replay_workflow(agent, user_id, req, initial) -> str:
    """Persist replay as a reusable workflow IR (map node expandable to batch)."""
    import json
    workflow = agent.schedule(
        user_id=user_id,
        name=f"Replay {req.trace_id[:8]}",
        task=f"Replay trace {req.trace_id} against {req.api_url}",
        when="+5s",
        context={
            "action": "graph",
            "graph": REPLAY_GRAPH,
            "input": {**initial, "host": None, "public_key": None, "secret_key": None,
                      "connection_id": req.connection_id, "destination_id": req.destination_id},
        },
        process_slug=f"replay_{req.trace_id[:8]}",
    )
    return workflow.id


register(
    name="replay_trace_to_api",
    fn=_replay_trace_to_api,
    description=(
        "Fetch a Langfuse trace's input/output, call an external API with that input, "
        "store the request+response, and return a structured diff between the original output and API response. "
        "Use when comparing LLM trace outputs against a target API or testing API regression."
    ),
    parameters={
        "trace_id": {"type": "string"},
        "connection_id": {"type": "string", "description": "Langfuse connection id"},
        "api_url": {"type": "string"},
        "method": {"type": "string", "enum": ["GET","POST","PUT","PATCH"], "default": "POST"},
        "auth": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["none","bearer","api_key","basic"]},
                "token": {"type": "string"},
                "header": {"type": "string"},
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": ["type"],
        },
        "input_mapping": {"type": "object", "description": "Optional key remapping trace.input → request body"},
        "destination_id": {"type": "string", "description": "Where to persist replay results"},
        "save_as_workflow": {"type": "boolean", "default": False},
    },
)
```

---

## UI: Replays page (apps/web/src/pages/ReplaysPage.tsx)

```tsx
// Table columns: trace_id | api_url | status_code | latency_ms | diff badge | ts
// Diff badge: "identical" (green) | "N diffs" (amber) | "error" (red)
// Row expand: side-by-side JSON diff panel (original_output left, response_body right)
// Highlight differing paths using diffs[].path
```

New daemon endpoint: `GET /api/replays?workflow_id=…` → SELECT from `replay_results` ORDER BY ts DESC.

---

## pytest: compare_outputs

```python
# packages/navbe_core/tests/test_compare.py
from navbe_core.steps import _diff

def test_identical_dicts():
    assert _diff({"a": 1}, {"a": 1}, "$") == []

def test_missing_key():
    diffs = _diff({"a": 1, "b": 2}, {"a": 1}, "$")
    assert any(d["path"] == "$.b" for d in diffs)

def test_nested_diff():
    diffs = _diff({"x": {"y": 1}}, {"x": {"y": 2}}, "$")
    assert diffs[0]["path"] == "$.x.y"
    assert diffs[0]["expected"] == 1
    assert diffs[0]["actual"] == 2

def test_list_length_diff():
    diffs = _diff([1, 2], [1, 2, 3], "$")
    assert any("length" in d["path"] for d in diffs)
```

---

## Done when

1. `replay_trace_to_api(trace_id=..., connection_id=..., api_url=..., auth={type:"bearer",token:"..."})` returns a `CompareResult`.
2. If `destination_id` is passed, row appears in `replay_results` DuckDB table.
3. UI Replays page shows the row with correct diff badge.
4. `pytest packages/navbe_core/tests/test_compare.py` passes (4 cases).
5. `save_as_workflow=True` creates a named workflow visible in `list_processes`.
