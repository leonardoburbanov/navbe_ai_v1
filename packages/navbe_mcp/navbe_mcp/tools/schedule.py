from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _schedule_workflow(
    agent: WorkflowAgent,
    user_id: str,
    name: str,
    task: str,
    when: str,
    context: dict | None = None,
    agent_id: str | None = None,
) -> dict:
    workflow = agent.schedule(user_id, name, task, when, context or {}, agent_id=agent_id)
    return {
        "workflow_id": workflow.id,
        "agent_id": workflow.agent_id,
        "name": workflow.name,
        "scheduled_at": workflow.scheduled_at.isoformat(),
        "recurring": workflow.cron_expression is not None,
        "message": f"Scheduled '{name}' for {workflow.scheduled_at.strftime('%A %b %d at %I:%M %p')} UTC",
    }


register(
    name="schedule_workflow",
    fn=_schedule_workflow,
    description=(
        "Schedule a workflow for an AI agent to execute at a future time. "
        "Use '+30s', '+1m', '+1h', '+1d', '+3d', 'monday 9am', or a cron expression for recurring workflows."
    ),
    parameters={
        "name": {"type": "string", "description": "Workflow name"},
        "task": {"type": "string", "description": "What the agent should do"},
        "when": {
            "type": "string",
            "description": "When to run: +30s, +1m, +1h, +1d, +3d, 'monday 9am', or a cron expression",
        },
        "context": {"type": "object", "description": "Context to preserve for the next run"},
        "agent_id": {
            "type": "string",
            "description": "Optional agent identifier; a uuid4 is generated if omitted",
        },
    },
)
