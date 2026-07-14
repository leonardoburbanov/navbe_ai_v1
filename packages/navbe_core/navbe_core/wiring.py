"""Static edge wiring rules for Workflow IR steps.

ponytail: adjacency dict only — typed ports when a second connector family appears.
"""

from __future__ import annotations

from typing import Any

# Allowed directed edges (predecessor → successor).
STEP_EDGES: list[tuple[str, str]] = [
    ("fetch_traces", "write_traces"),
    ("write_traces", "refresh_retailer_mart"),
    ("refresh_retailer_mart", "build_retailer_report"),
    ("build_retailer_report", "send_email_report"),
    ("fetch_trace", "call_api"),
    ("call_api", "compare_outputs"),
    ("compare_outputs", "store_replay"),
]

# NL aliases → registered step ids
STEP_ALIASES: dict[str, str] = {
    "fetch traces": "fetch_traces",
    "fetch_traces": "fetch_traces",
    "write traces": "write_traces",
    "write_traces": "write_traces",
    "refresh retailer mart": "refresh_retailer_mart",
    "retailer mart": "refresh_retailer_mart",
    "refresh_retailer_mart": "refresh_retailer_mart",
    "build retailer report": "build_retailer_report",
    "retailer report": "build_retailer_report",
    "build_retailer_report": "build_retailer_report",
    "send email": "send_email_report",
    "send email report": "send_email_report",
    "send_email_report": "send_email_report",
    "fetch trace": "fetch_trace",
    "fetch_trace": "fetch_trace",
    "call api": "call_api",
    "call_api": "call_api",
    "compare": "compare_outputs",
    "compare outputs": "compare_outputs",
    "compare_outputs": "compare_outputs",
    "store replay": "store_replay",
    "store_replay": "store_replay",
}

KNOWN_STEPS: frozenset[str] = frozenset({dst for _, dst in STEP_EDGES} | {src for src, _ in STEP_EDGES})


def resolve_step_hint(hint: str) -> str | None:
    """Map a free-text hint to a registered step id, or None."""
    key = hint.strip().lower()
    if key in STEP_ALIASES:
        return STEP_ALIASES[key]
    # substring match
    for alias, step_id in STEP_ALIASES.items():
        if alias in key:
            return step_id
    if key in KNOWN_STEPS:
        return key
    return None


def predecessors_of(step: str) -> list[str]:
    """Steps that may feed into ``step``."""
    return [src for src, dst in STEP_EDGES if dst == step]


def successors_of(step: str) -> list[str]:
    """Steps that ``step`` may feed into."""
    return [dst for src, dst in STEP_EDGES if src == step]


def wire_step(existing_nodes: list[str], new_step: str) -> dict[str, Any]:
    """Suggest edges when adding ``new_step`` to an existing graph.

    Returns:
      {"edges": [[src, dst], ...]} when unambiguous, or
      {"needs_input": True, "candidates": [[src, dst], ...], "message": str}.
    """
    if new_step not in KNOWN_STEPS:
        return {
            "needs_input": True,
            "candidates": [],
            "message": f"Unknown step {new_step!r}. Known: {sorted(KNOWN_STEPS)}",
        }
    existing = set(existing_nodes)
    preds = [p for p in predecessors_of(new_step) if p in existing]
    succs = [s for s in successors_of(new_step) if s in existing]
    edges: list[list[str]] = []
    if len(preds) == 1:
        edges.append([preds[0], new_step])
    if len(succs) == 1:
        edges.append([new_step, succs[0]])
    if len(preds) > 1 or len(succs) > 1:
        candidates = [[p, new_step] for p in preds] + [[new_step, s] for s in succs]
        return {
            "needs_input": True,
            "candidates": candidates,
            "edges": edges,
            "message": (
                f"Ambiguous wiring for {new_step}: call connect_workflow_steps "
                f"with one of {candidates}"
            ),
        }
    if not edges and existing_nodes:
        # Fallback: attach after the last node if no rule matched
        return {
            "needs_input": True,
            "candidates": [[existing_nodes[-1], new_step]],
            "edges": [],
            "message": (
                f"No wiring rule from existing nodes to {new_step}. "
                f"Call connect_workflow_steps(source={existing_nodes[-1]!r}, target={new_step!r})."
            ),
        }
    return {"edges": edges, "needs_input": False}


def recompute_entry(nodes: list[str], edges: list[list[str]]) -> str:
    """Pick entry as the node with no incoming edges (first such, else nodes[0])."""
    if not nodes:
        raise ValueError("Cannot compute entry for empty graph")
    targets = {e[1] for e in edges if len(e) >= 2}
    for n in nodes:
        if n not in targets:
            return n
    return nodes[0]


assert wire_step(["fetch_traces"], "write_traces")["edges"] == [["fetch_traces", "write_traces"]]
assert wire_step(["fetch_traces", "write_traces"], "refresh_retailer_mart")["edges"] == [
    ["write_traces", "refresh_retailer_mart"]
]
