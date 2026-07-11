"""LangGraph step handlers for Navbe workflows."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import duckdb
from navbe_connectors.langfuse import fetch_last_traces
from navbe_destinations.duckdb import ensure_schema, write_observations, write_traces
from navbe_transforms.tags import MART_REFRESH_SQL

StepFn = Callable[[dict], dict]

_steps: dict[str, dict[str, Any]] = {}


def step(name: str, retries: int = 0) -> Callable[[StepFn], StepFn]:
    """Register a named step function with optional retries."""

    def decorator(fn: StepFn) -> StepFn:
        _steps[name] = {"fn": fn, "retries": retries}
        return fn

    return decorator


def get_step(name: str) -> StepFn:
    """Return a registered step, wrapping retries if configured."""
    if name not in _steps:
        raise ValueError(f"Unknown step: {name}")
    entry = _steps[name]
    return _with_retries(entry["fn"], entry["retries"])


def _with_retries(fn: StepFn, retries: int) -> StepFn:
    def wrapped(state: dict) -> dict:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return fn(state)
            except Exception as e:  # ponytail: retry any exception; narrow if a step needs it
                last = e
                if attempt < retries:
                    time.sleep(min(2**attempt, 8))  # ponytail: blocking backoff, cap 8s
        if last is None:
            raise RuntimeError(f"step failed with no exception after {retries + 1} attempts")
        raise last

    return wrapped


def _parse_since(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@step("fetch_traces", retries=3)
def fetch_traces(state: dict) -> dict:
    """Pull a bounded page of Langfuse traces, optionally since a watermark."""
    traces = fetch_last_traces(
        state["host"],
        state["public_key"],
        state["secret_key"],
        limit=state.get("limit", 50),
        include_observations=state.get("include_observations", False),
        since=_parse_since(state.get("since")),
    )
    return {"traces": traces}


@step("write_traces")
def write_traces_step(state: dict) -> dict:
    """Upsert traces (and optional observations) into the destination."""
    result = write_traces(
        state["traces"],
        state["dest_type"],
        state["dest_config"],
        state["workflow_id"],
        mode=state.get("mode", "append"),
    )
    if state.get("include_observations"):
        result.update(
            write_observations(
                state["traces"],
                state["dest_type"],
                state["dest_config"],
                mode=state.get("mode", "append"),
            )
        )
    return {**result, "trace_count": len(state["traces"])}


@step("refresh_retailer_mart")
def refresh_retailer_mart(state: dict) -> dict:
    """Rebuild mart_retailer_token_cost_daily from traces tags."""
    if state.get("dest_type") != "duckdb":
        return {"mart_refreshed": False, "reason": "duckdb only"}
    db_path = state["dest_config"].get("db_path")
    if not db_path:
        return {"mart_refreshed": False, "reason": "no db_path"}
    con = duckdb.connect(db_path)
    try:
        ensure_schema(con)
        con.execute(MART_REFRESH_SQL)
    finally:
        con.close()
    return {"mart_refreshed": True}


def _diff(expected: object, actual: object, path: str) -> list[dict]:
    """Recursive JSON diff. Returns list of {path, expected, actual, match}."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out: list[dict] = []
        for k in expected.keys() | actual.keys():
            out.extend(_diff(expected.get(k), actual.get(k), f"{path}.{k}"))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        out = []
        for i, (e, a) in enumerate(zip(expected, actual, strict=False)):
            out.extend(_diff(e, a, f"{path}[{i}]"))
        if len(expected) != len(actual):
            out.append(
                {
                    "path": f"{path}.length",
                    "expected": len(expected),
                    "actual": len(actual),
                    "match": False,
                }
            )
        return out
    if expected == actual:
        return []
    return [{"path": path, "expected": expected, "actual": actual, "match": False}]


def _decrypt_auth(auth_cfg: dict) -> dict:
    """Decrypt Fernet-wrapped token/password when saved in a workflow."""
    if not auth_cfg.get("_encrypted"):
        return auth_cfg
    from navbe_core.secrets import decrypt

    out = dict(auth_cfg)
    if out.get("token"):
        out["token"] = decrypt(out["token"])
    if out.get("password"):
        out["password"] = decrypt(out["password"])
    out.pop("_encrypted", None)
    return out


@step("fetch_trace", retries=2)
def fetch_trace(state: dict) -> dict:
    """Fetch a single Langfuse trace by ID including input/output."""
    import httpx

    response = httpx.get(
        f"{state['host'].rstrip('/')}/api/public/traces/{state['trace_id']}",
        auth=(state["public_key"], state["secret_key"]),
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "trace_input": data.get("input"),
        "trace_output": data.get("output"),
        "trace_metadata": data.get("metadata") or {},
    }


@step("call_api", retries=1)
def call_api(state: dict) -> dict:
    """Call the target API with mapped body and auth."""
    import time as _time

    import httpx

    auth_cfg = _decrypt_auth(dict(state.get("auth") or {"type": "none"}))
    mapping = state.get("input_mapping") or {}
    body = dict(state.get("trace_input") or {})
    for src, dst in mapping.items():
        if src in body:
            body[dst] = body.pop(src)

    headers: dict[str, str] = {}
    auth = None
    auth_type = auth_cfg.get("type", "none")
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth_cfg.get('token')}"
    elif auth_type == "api_key":
        headers[auth_cfg.get("header") or "Authorization"] = str(auth_cfg.get("token") or "")
    elif auth_type == "basic":
        auth = (auth_cfg.get("username") or "", auth_cfg.get("password") or "")

    method = state.get("method", "POST")
    kwargs: dict[str, Any] = {"headers": headers, "auth": auth, "timeout": 60.0}
    if method != "GET":
        kwargs["json"] = body

    t0 = _time.perf_counter()
    response = httpx.request(method, state["api_url"], **kwargs)
    latency_ms = (_time.perf_counter() - t0) * 1000

    try:
        response_body: object = response.json()
    except Exception:
        response_body = {"_raw": response.text}

    return {
        "api_status_code": response.status_code,
        "api_response": response_body,
        "api_latency_ms": latency_ms,
        "api_request_body": body,
    }


@step("compare_outputs")
def compare_outputs(state: dict) -> dict:
    """Structured JSON diff: trace output vs API response."""
    original = state.get("trace_output") or {}
    actual = state.get("api_response") or {}
    diffs = _diff(original, actual, "$")
    return {
        "compare_result": {
            "identical": len(diffs) == 0,
            "diff_count": len(diffs),
            "diffs": diffs,
        }
    }


@step("store_replay")
def store_replay(state: dict) -> dict:
    """Persist replay result into DuckDB replay_results when a destination is set."""
    import json as _json
    import uuid
    from datetime import UTC, datetime

    dest_config = state.get("dest_config")
    if not dest_config or not dest_config.get("db_path"):
        return {"replay_id": ""}

    db_path = dest_config["db_path"]
    replay_id = str(uuid.uuid4())
    con = duckdb.connect(db_path)
    try:
        ensure_schema(con)
        con.execute(
            """
            INSERT INTO replay_results
                (id, trace_id, api_url, request_body, response_body, status_code,
                 latency_ms, original_output, diff_summary, ts, extras)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                replay_id,
                state["trace_id"],
                state["api_url"],
                _json.dumps(state.get("api_request_body")),
                _json.dumps(state.get("api_response")),
                state.get("api_status_code"),
                state.get("api_latency_ms"),
                _json.dumps(state.get("trace_output")),
                _json.dumps(state.get("compare_result")),
                datetime.now(UTC).isoformat(),
                None,
            ],
        )
    finally:
        con.close()
    return {"replay_id": replay_id}
