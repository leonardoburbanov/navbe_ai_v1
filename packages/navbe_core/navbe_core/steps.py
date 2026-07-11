import time
from collections.abc import Callable
from typing import Any

from navbe_connectors.langfuse import fetch_last_traces
from navbe_destinations.duckdb import write_observations, write_traces

StepFn = Callable[[dict], dict]

_steps: dict[str, dict[str, Any]] = {}


def step(name: str, retries: int = 0) -> Callable[[StepFn], StepFn]:
    def decorator(fn: StepFn) -> StepFn:
        _steps[name] = {"fn": fn, "retries": retries}
        return fn

    return decorator


def get_step(name: str) -> StepFn:
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


@step("fetch_traces", retries=3)
def fetch_traces(state: dict) -> dict:
    traces = fetch_last_traces(
        state["host"],
        state["public_key"],
        state["secret_key"],
        limit=state.get("limit", 50),
        include_observations=state.get("include_observations", False),
    )
    return {"traces": traces}


@step("write_traces")
def write_traces_step(state: dict) -> dict:
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
