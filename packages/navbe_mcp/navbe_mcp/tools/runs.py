from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _list_workflow_runs(
    agent: WorkflowAgent, user_id: str, workflow_id: str, page: int = 1, page_size: int = 20
) -> dict:
    return agent.list_runs(workflow_id, user_id, page=page, page_size=page_size)


register(
    name="list_workflow_runs",
    fn=_list_workflow_runs,
    description="List a workflow's previous runs, most recent first, paginated.",
    parameters={
        "workflow_id": {"type": "string", "description": "The workflow ID"},
        "page": {"type": "integer", "description": "1-indexed page number (default 1)"},
        "page_size": {"type": "integer", "description": "Runs per page, max 100 (default 20)"},
    },
)
