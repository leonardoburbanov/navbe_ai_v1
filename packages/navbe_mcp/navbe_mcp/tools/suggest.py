from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _suggest_workflow(agent: WorkflowAgent, user_id: str, hint: str) -> dict:
    return agent.suggest(user_id, hint)


register(
    name="suggest_workflow",
    fn=_suggest_workflow,
    description=(
        "Given a free-text hint naming a data source (e.g. 'monitor langfuse traces'), "
        "propose a DAG workflow: source, steps, destination, and dedup strategy, as "
        "markdown plus a ready-to-use `context` for schedule_workflow. Read-only — "
        "nothing is scheduled until you call schedule_workflow with the returned context "
        "and a `when`."
    ),
    parameters={
        "hint": {
            "type": "string",
            "description": "Free text naming the data source, e.g. 'langfuse traces'",
        },
    },
)
