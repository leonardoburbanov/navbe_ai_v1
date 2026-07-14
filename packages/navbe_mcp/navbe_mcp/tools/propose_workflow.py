"""MCP tools: propose_workflow / confirm_workflow."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _propose_workflow(agent: WorkflowAgent, user_id: str, hint: str) -> dict:
    """NL intent → draft IR (no persist)."""
    return agent.propose_workflow(user_id, hint)


def _confirm_workflow(
    agent: WorkflowAgent,
    user_id: str,
    draft: dict,
    when: str = "+5s",
    name: str | None = None,
    slug: str | None = None,
) -> dict:
    """Persist a propose_workflow draft."""
    return agent.confirm_workflow(user_id, draft, when=when, name=name, slug=slug)


register(
    name="propose_workflow",
    fn=_propose_workflow,
    description=(
        "Given a free-text hint (e.g. 'monitor langfuse traces'), propose a workflow "
        "draft: graph, bindings, trigger. Read-only — call confirm_workflow to persist."
    ),
    parameters={
        "hint": {
            "type": "string",
            "description": "Free text naming the data source / intent",
        },
    },
)

register(
    name="confirm_workflow",
    fn=_confirm_workflow,
    description=(
        "Persist a propose_workflow draft as a scheduled workflow. "
        "Pass the draft object (or equivalent with graph + input). "
        "Optional when= cron or relative time."
    ),
    parameters={
        "draft": {"type": "object", "description": "Draft from propose_workflow"},
        "when": {
            "type": "string",
            "description": "Schedule: +5s, cron, or 'manual'",
        },
        "name": {"type": "string", "description": "Optional workflow display name"},
        "slug": {"type": "string", "description": "Optional friendly slug"},
    },
)
