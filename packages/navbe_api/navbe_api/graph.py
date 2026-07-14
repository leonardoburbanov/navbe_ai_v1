"""Shape Workflow IR into a React Flow–friendly graph payload."""

from __future__ import annotations

import json
import re
from typing import Any

# Step name → React Flow custom node type
_STEP_NODE_TYPES: dict[str, str] = {
    "fetch_traces": "connector",
    "fetch_trace": "connector",
    "write_traces": "destination",
    "store_replay": "destination",
    "refresh_retailer_mart": "transform",
    "build_retailer_report": "transform",
    "compare_outputs": "transform",
    "call_api": "control",
    "send_email_report": "control",
}


def _label(step: str) -> str:
    """Humanize a step id: fetch_traces → Fetch Traces."""
    return re.sub(r"_+", " ", step).strip().title()


def _node_type(step: str) -> str:
    return _STEP_NODE_TYPES.get(step, "control")


def workflow_to_flow_graph(context_json: str) -> dict:
    """Convert persisted workflow.context into nodes/edges for the DAG canvas.

    Positions are placeholders (0,0) — the Control UI runs dagre layout client-side.
    """
    from navbe_core.sources import SOURCES

    context = json.loads(context_json) if context_json else {}
    graph = context.get("graph") or {}
    nodes_raw: list[str] = list(graph.get("nodes") or [])
    # Match agent soft-upgrade so the canvas shows report + email steps.
    if "refresh_retailer_mart" in nodes_raw and "build_retailer_report" not in nodes_raw:
        graph = SOURCES["langfuse"]["graph"]
        nodes_raw = list(graph.get("nodes") or [])
    edges_raw: list[list[str]] = list(graph.get("edges") or [])

    nodes = [
        {
            "id": step,
            "type": _node_type(step),
            "data": {
                "label": _label(step),
                "step": step,
                "status": "idle",
            },
            "position": {"x": 0, "y": 0},
        }
        for step in nodes_raw
    ]
    edges = [
        {
            "id": f"e-{src}-{dst}",
            "source": src,
            "target": dst,
            "animated": False,
        }
        for src, dst in edges_raw
    ]
    return {"nodes": nodes, "edges": edges}


def workflow_bindings(context_json: str, repo: Any, user_id: str) -> dict:
    """Trigger + bound connector/destination labels for the Workflows detail panel."""
    context = json.loads(context_json) if context_json else {}
    inp = context.get("input") or {}
    trigger = context.get("trigger") or {}
    connector_id = inp.get("connector_id") or inp.get("connection_id")
    destination_id = inp.get("destination_id")
    connector_name = None
    destination_name = None
    if connector_id:
        c = repo.get_connector(connector_id, user_id)
        connector_name = c.name if c else None
    if destination_id:
        d = repo.get_destination(destination_id, user_id)
        destination_name = d.name if d else None
    graph = context.get("graph") or {}
    return {
        "trigger": trigger,
        "connector_id": connector_id,
        "connector_name": connector_name,
        "destination_id": destination_id,
        "destination_name": destination_name,
        "entry": graph.get("entry"),
        "node_count": len(graph.get("nodes") or []),
    }
