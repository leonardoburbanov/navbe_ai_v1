from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _suggest_workflow(agent: WorkflowAgent, user_id: str, hint: str) -> dict:
    """Deprecated alias → propose_workflow."""
    return agent.propose_workflow(user_id, hint)


register(
    name="suggest_workflow",
    fn=_suggest_workflow,
    description=(
        "Deprecated alias for propose_workflow. "
        "Given a free-text hint, propose a DAG draft (no persist)."
    ),
    parameters={
        "hint": {
            "type": "string",
            "description": "Free text naming the data source, e.g. 'langfuse traces'",
        },
    },
)
