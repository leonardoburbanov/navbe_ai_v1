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
