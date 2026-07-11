import json

from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _recall_workflow(agent: WorkflowAgent, user_id: str, workflow_id: str) -> dict:
    result = agent.recall(workflow_id, user_id)
    workflow = result["workflow"]
    last_run = result["last_run"]

    return {
        "workflow_id": workflow.id,
        "agent_id": workflow.agent_id,
        "name": workflow.name,
        "status": workflow.status,
        "task": workflow.task_description,
        "scheduled_at": workflow.scheduled_at.isoformat(),
        "cron_expression": workflow.cron_expression,
        "context": result["context"],
        "last_run": (
            {
                "status": last_run.status,
                "started_at": last_run.started_at.isoformat(),
                "completed_at": last_run.completed_at.isoformat()
                if last_run.completed_at
                else None,
                "output": json.loads(last_run.output) if last_run.output else None,
                "error": last_run.error,
            }
            if last_run
            else None
        ),
    }


register(
    name="recall_workflow",
    fn=_recall_workflow,
    description="Recall a workflow's details, persisted context, and the result of its last run.",
    parameters={
        "workflow_id": {"type": "string", "description": "The workflow ID to recall"},
    },
)
