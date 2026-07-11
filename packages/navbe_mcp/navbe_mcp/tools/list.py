from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _list_workflows(agent: WorkflowAgent, user_id: str) -> dict:
    workflows = agent.list(user_id)
    return {
        "count": len(workflows),
        "workflows": [
            {
                "workflow_id": w.id,
                "agent_id": w.agent_id,
                "name": w.name,
                "status": w.status,
                "task": w.task_description,
                "scheduled_at": w.scheduled_at.isoformat(),
                "cron_expression": w.cron_expression,
                "recurring": w.cron_expression is not None,
            }
            for w in workflows
        ],
    }


register(
    name="list_workflows",
    fn=_list_workflows,
    description="List all workflows for the current user, including status and schedule.",
    parameters={},
)
