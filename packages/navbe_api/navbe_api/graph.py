"""Shape Workflow IR into a React Flow–friendly graph payload."""

from __future__ import annotations

import json
import re

# Step name → React Flow custom node type
_STEP_NODE_TYPES: dict[str, str] = {
    "fetch_traces": "connector",
    "write_traces": "destination",
    "refresh_retailer_mart": "transform",
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
    context = json.loads(context_json) if context_json else {}
    graph = context.get("graph") or {}
    nodes_raw: list[str] = list(graph.get("nodes") or [])
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
