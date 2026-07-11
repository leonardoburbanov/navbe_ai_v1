"""MCP tool: replay_trace_to_api — MVP B."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, cast

from navbe_core.agent import WorkflowAgent
from navbe_core.graph import build_graph
from navbe_core.live_url import live_process_url
from navbe_core.models_replay import CompareResult, ReplayRequest, ReplayResult
from navbe_core.secrets import encrypt

from navbe_mcp.registry import register

REPLAY_GRAPH = {
    "entry": "fetch_trace",
    "nodes": ["fetch_trace", "call_api", "compare_outputs", "store_replay"],
    "edges": [
        ["fetch_trace", "call_api"],
        ["call_api", "compare_outputs"],
        ["compare_outputs", "store_replay"],
    ],
}

HttpMethod = Literal["GET", "POST", "PUT", "PATCH"]
_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH"}


def _encrypt_auth(auth: dict) -> dict:
    """Encrypt token/password before persisting in workflow IR."""
    out = dict(auth)
    if out.get("token"):
        out["token"] = encrypt(out["token"])
    if out.get("password"):
        out["password"] = encrypt(out["password"])
    out["_encrypted"] = True
    return out


def _run_output(state: dict, req: ReplayRequest) -> dict[str, Any]:
    """JSON-safe run output for the Runs page (no secrets)."""
    return {
        "trace_id": req.trace_id,
        "api_url": req.api_url,
        "method": req.method,
        "replay_id": state.get("replay_id") or "",
        "api_status_code": state.get("api_status_code"),
        "api_latency_ms": state.get("api_latency_ms"),
        "compare_result": state.get("compare_result"),
        "original_output": state.get("trace_output"),
        "response_body": state.get("api_response"),
    }


def _save_replay_workflow(
    agent: WorkflowAgent,
    user_id: str,
    req: ReplayRequest,
    auth_plain: dict,
    state: dict,
) -> str:
    """Persist replay IR + record the inline execution as a WorkflowRun.

    Does not schedule a +Ns tick — that only fires in the process that
    registered it, so one-shot MCP/tool calls never created runs.
    Re-run later via run_workflow / run_now.
    """
    workflow = agent.repo.create_workflow(
        user_id=user_id,
        name=f"Replay {req.trace_id[:8]}",
        task=f"Replay trace {req.trace_id} against {req.api_url}",
        scheduled_at=datetime.utcnow(),
        process_slug=f"replay_{req.trace_id[:8]}",
        context={
            "action": "graph",
            "graph": REPLAY_GRAPH,
            "input": {
                "trace_id": req.trace_id,
                "connection_id": req.connection_id,
                "connector_id": req.connection_id,
                "destination_id": req.destination_id,
                "api_url": req.api_url,
                "method": req.method,
                "auth": _encrypt_auth(auth_plain),
                "input_mapping": req.input_mapping,
            },
        },
    )
    run = agent.repo.start_run(workflow.id)
    agent.repo.complete_run(run.id, _run_output(state, req))
    agent.repo.update_workflow_status(workflow.id, "completed")
    return workflow.id


def _replay_trace_to_api(
    agent: WorkflowAgent,
    user_id: str,
    trace_id: str,
    connection_id: str,
    api_url: str,
    auth: dict,
    method: str = "POST",
    input_mapping: dict | None = None,
    destination_id: str | None = None,
    save_as_workflow: bool = False,
) -> dict:
    """Fetch Langfuse trace I/O, call target API, compare, optionally persist."""
    req = ReplayRequest(
        trace_id=trace_id,
        connection_id=connection_id,
        api_url=api_url,
        method=cast(HttpMethod, method if method in _METHODS else "POST"),
        auth=auth,  # type: ignore[arg-type]
        input_mapping=input_mapping or {},
        destination_id=destination_id,
        save_as_workflow=save_as_workflow,
    )

    connector = agent.repo.get_connector(req.connection_id, user_id)
    if connector is None:
        return {
            "error": f"Connection not found: {req.connection_id}",
            "next_step": "call list_connectors",
        }

    dest_config = None
    if req.destination_id:
        dest = agent.repo.get_destination(req.destination_id, user_id)
        if dest is None:
            return {
                "error": f"Destination not found: {req.destination_id}",
                "next_step": "call list_destinations",
            }
        dest_config = json.loads(dest.config)

    initial: dict = {
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
    state: dict = dict(initial)
    for update in compiled.stream(state, stream_mode="updates"):
        for _, step_state in update.items():
            state = step_state

    workflow_id = None
    if req.save_as_workflow:
        workflow_id = _save_replay_workflow(
            agent, user_id, req, req.auth.model_dump(), state
        )

    compare_raw = state.get("compare_result") or {
        "identical": True,
        "diff_count": 0,
        "diffs": [],
    }
    replay_id = state.get("replay_id")
    status_code = state.get("api_status_code")
    latency_ms = state.get("api_latency_ms")
    from navbe_core.config import settings

    live_url: str | None = None
    if workflow_id:
        live_url = live_process_url(workflow_id=workflow_id, page="dag")
        next_step = f"Open live_url to watch the DAG: {live_url}"
    elif req.destination_id:
        live_url = f"{settings.UI_URL.rstrip('/')}/?page=replays"
        next_step = f"Open live_url for the experiment report: {live_url}"
    else:
        next_step = "pass destination_id to persist results"

    result = ReplayResult(
        replay_id=str(replay_id) if replay_id else "",
        trace_id=req.trace_id,
        status_code=int(status_code) if isinstance(status_code, (int, float, str)) else 0,
        latency_ms=float(latency_ms) if isinstance(latency_ms, (int, float, str)) else 0.0,
        compare=CompareResult.model_validate(compare_raw),
        workflow_id=workflow_id,
        live_url=live_url,
        next_step=next_step,
    )
    return result.model_dump()


register(
    name="replay_trace_to_api",
    fn=_replay_trace_to_api,
    description=(
        "Fetch a Langfuse trace's input/output, call an external API with that input, "
        "store the request+response, and return a structured diff between the original "
        "output and API response."
    ),
    parameters={
        "trace_id": {"type": "string"},
        "connection_id": {
            "type": "string",
            "description": "Langfuse connector id",
        },
        "api_url": {"type": "string"},
        "method": {
            "type": "string",
            "enum": ["GET", "POST", "PUT", "PATCH"],
            "description": "HTTP method (default POST)",
        },
        "auth": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["none", "bearer", "api_key", "basic"],
                },
                "token": {"type": "string"},
                "header": {"type": "string"},
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": ["type"],
        },
        "input_mapping": {
            "type": "object",
            "description": "Optional key remapping trace.input → request body",
        },
        "destination_id": {
            "type": "string",
            "description": "DuckDB destination to persist replay_results",
        },
        "save_as_workflow": {
            "type": "boolean",
            "description": "Also save as a reusable named process",
        },
    },
)
