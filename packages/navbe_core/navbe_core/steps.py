"""LangGraph step handlers for Navbe workflows."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import duckdb
from navbe_connectors.langfuse import fetch_last_traces
from navbe_destinations.duckdb import ensure_schema, write_observations, write_traces
from navbe_transforms.tags import MART_REFRESH_SQL

from navbe_core.config import DATA_DIR

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
    dest_config = state.get("dest_config") or {}
    # Same default as write_traces / query_destination when config omits db_path.
    db_path = dest_config.get("db_path") or os.path.join(str(DATA_DIR), "langfuse.duckdb")
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


def _response_texts(payload: object) -> list[str | None]:
    """Extract agent message texts from a plan-execute style output payload."""
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if not isinstance(response, list):
        return []
    texts: list[str | None] = []
    for item in response:
        if isinstance(item, dict):
            texts.append(None if item.get("text") is None else str(item.get("text")))
        elif isinstance(item, str):
            texts.append(item)
        else:
            texts.append(None)
    return texts


def _experiment_messages(original: object, actual: object) -> tuple[list[dict], bool]:
    """Compare agent message texts — primary signal for replay experiments."""
    orig = _response_texts(original)
    act = _response_texts(actual)
    n = max(len(orig), len(act))
    rows: list[dict] = []
    all_match = True
    for i in range(n):
        expected = orig[i] if i < len(orig) else None
        got = act[i] if i < len(act) else None
        match = expected == got
        if not match:
            all_match = False
        rows.append(
            {
                "index": i,
                "expected": expected,
                "actual": got,
                "match": match,
            }
        )
    if n == 0:
        expected = None if original in (None, {}) else str(original)
        got = None if actual in (None, {}) else str(actual)
        match = expected == got
        rows = [{"index": 0, "expected": expected, "actual": got, "match": match}]
        all_match = match
    return rows, all_match


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
    # LangGraph/Langfuse agent traces wrap the HTTP payload under kwargs.request.
    kwargs = body.get("kwargs")
    if isinstance(kwargs, dict) and isinstance(kwargs.get("request"), dict):
        body = dict(kwargs["request"])
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
    """Structured JSON diff + experiment message report (trace vs API)."""
    original = state.get("trace_output") or {}
    actual = state.get("api_response") or {}
    diffs = _diff(original, actual, "$")
    experiment_messages, messages_identical = _experiment_messages(original, actual)
    return {
        "compare_result": {
            "identical": len(diffs) == 0,
            "diff_count": len(diffs),
            "diffs": diffs,
            "experiment_messages": experiment_messages,
            "messages_identical": messages_identical,
        }
    }


@step("store_replay")
def store_replay(state: dict) -> dict:
    """Persist replay result into DuckDB replay_results when a destination is set."""
    import json as _json
    import uuid
    from datetime import UTC, datetime

    dest_config = state.get("dest_config")
    if dest_config is None:
        return {"replay_id": ""}

    # Same default as write_traces / query when config omits db_path.
    db_path = dest_config.get("db_path") or os.path.join(str(DATA_DIR), "langfuse.duckdb")
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


def _duckdb_path(state: dict) -> str:
    dest_config = state.get("dest_config") or {}
    return dest_config.get("db_path") or os.path.join(str(DATA_DIR), "langfuse.duckdb")


@step("build_retailer_report")
def build_retailer_report(state: dict) -> dict:
    """Build DoD / 7d / projection payload from mart_retailer_token_cost_daily."""
    from navbe_transforms.retailer_report import build_retailer_report_payload

    if state.get("dest_type") not in (None, "duckdb"):
        return {"error": "duckdb destination required for retailer report"}
    db_path = _duckdb_path(state)
    con = duckdb.connect(db_path, read_only=True)
    try:
        payload = build_retailer_report_payload(con)
    finally:
        con.close()
    return {
        "report_payload": payload.model_dump(),
        "report_date": payload.report_date,
    }


@step("send_email_report")
def send_email_report(state: dict) -> dict:
    """Render HTML and either preview to disk or send via Resend/SMTP."""
    from navbe_notify import bus as events
    from navbe_notify.email_report import (
        email_configured,
        render_retailer_daily_html,
        save_report_preview,
        send_html_email,
    )

    from navbe_core.models_report import RetailerReportPayload

    raw = state.get("report_payload")
    if not raw:
        return {"error": "missing report_payload", "email_sent": False}
    payload = RetailerReportPayload.model_validate(raw)
    html = render_retailer_daily_html(payload)
    process_slug = state.get("process_slug") or "langfuse_daily_report"
    topic = f"process.{process_slug}"
    preview_only = state.get("mode") == "preview" or state.get("preview_only")

    path = save_report_preview(html, payload.report_date)
    if preview_only:
        events.publish(
            topic,
            "report.previewed",
            {"report_date": payload.report_date, "path": str(path), "totals": payload.totals},
        )
        return {
            "email_sent": False,
            "preview_path": str(path),
            "report_date": payload.report_date,
            "totals": payload.totals,
        }

    if not email_configured():
        events.publish(topic, "report.failed", {"error": "email not configured"})
        return {
            "email_sent": False,
            "needs_input": {
                "fields": ["api_key", "from_addr"],
                "hint": "call configure_resend (or configure_email for SMTP)",
            },
            "preview_path": str(path),
            "next_step": "configure_resend",
        }

    to_raw = state.get("email_to") or []
    if isinstance(to_raw, str):
        to_list = [a.strip() for a in to_raw.split(",") if a.strip()]
    else:
        to_list = list(to_raw)
    if not to_list:
        return {
            "email_sent": False,
            "needs_input": {"fields": ["email_to"], "hint": "provide recipient list"},
            "preview_path": str(path),
        }

    subject = f"Navbe daily retailer report — {payload.report_date}"
    try:
        send_meta = send_html_email(to_list, subject, html)
    except Exception as e:
        events.publish(topic, "report.failed", {"error": str(e), "report_date": payload.report_date})
        return {"email_sent": False, "error": str(e), "preview_path": str(path)}

    events.publish(
        topic,
        "report.sent",
        {
            "report_date": payload.report_date,
            "to": to_list,
            "path": str(path),
            "totals": payload.totals,
            "provider": send_meta.get("provider"),
        },
    )
    return {
        "email_sent": True,
        "preview_path": str(path),
        "report_date": payload.report_date,
        "to": to_list,
        "totals": payload.totals,
        "provider": send_meta.get("provider"),
    }
