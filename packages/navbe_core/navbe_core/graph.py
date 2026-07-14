"""Compile Workflow IR into a LangGraph StateGraph."""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, StateGraph

from navbe_core.steps import StepFn, get_step


def _merging(fn: StepFn, step_name: str) -> StepFn:
    # A bare `dict` schema gives StateGraph a single whole-state channel that
    # REPLACES on each node's return, rather than per-key channels that merge.
    # Merge the node's partial update onto the incoming state ourselves so
    # steps can keep returning partial dicts.
    # Sprint 10: apply per-step connector creds from state["_step_creds"].
    def wrapped(state: dict) -> dict:
        creds = (state.get("_step_creds") or {}).get(step_name)
        if creds:
            state = {**state, **creds}
        return {**state, **fn(state)}

    return wrapped


def _validate(entry: str, nodes: list[str], edges: list[tuple[str, str]]) -> None:
    if entry not in nodes:
        raise ValueError(f"Graph entry '{entry}' is not in nodes: {nodes}")
    for src, dst in edges:
        if src not in nodes:
            raise ValueError(f"Edge source '{src}' is not in nodes: {nodes}")
        if dst not in nodes:
            raise ValueError(f"Edge target '{dst}' is not in nodes: {nodes}")


def build_graph(definition: dict) -> Any:
    """Build and compile a LangGraph from a Workflow IR definition dict."""
    entry = definition["entry"]
    nodes = definition["nodes"]
    edges = [tuple(e) for e in definition["edges"]]
    _validate(entry, nodes, edges)

    # ponytail: StateGraph(dict) typing is loose vs LangGraph's NodeInput protocols
    g: Any = StateGraph(cast(Any, dict))
    for name in nodes:
        g.add_node(name, _merging(get_step(name), name))
    for src, dst in edges:
        g.add_edge(src, dst)
    for name in nodes:
        if not any(src == name for src, _ in edges):
            g.add_edge(name, END)
    g.set_entry_point(entry)
    return g.compile()
