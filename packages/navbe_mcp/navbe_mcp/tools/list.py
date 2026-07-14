import json

from navbe_core.agent import WorkflowAgent, _workflow_slug

from navbe_mcp.registry import register


def _list_workflows(agent: WorkflowAgent, user_id: str) -> dict:
    """List workflows with slug, schedule, node count, last run."""
    workflows = agent.list(user_id)
    rows = []
    for w in workflows:
        ctx = json.loads(w.context or "{}")
        graph = ctx.get("graph") or {}
        nodes = list(graph.get("nodes") or [])
        last = agent.repo.get_last_run(w.id)
        friendly = _workflow_slug(w)
        rows.append(
            {
                "workflow_id": w.id,
                "agent_id": w.agent_id,
                "name": w.name,
                "slug": friendly,
                "process_slug": friendly,
                "status": w.status,
                "task": w.task_description,
                "scheduled_at": w.scheduled_at.isoformat(),
                "cron_expression": w.cron_expression,
                "recurring": w.cron_expression is not None,
                "node_count": len(nodes),
                "nodes": nodes,
                "last_run": (
                    {
                        "run_id": last.id,
                        "status": last.status,
                        "started_at": last.started_at.isoformat(),
                        "completed_at": (
                            last.completed_at.isoformat() if last.completed_at else None
                        ),
                    }
                    if last
                    else None
                ),
            }
        )
    return {
        "count": len(rows),
        "workflows": rows,
        "next_step": "call get_workflow_status(slug=...) or open Workflows in the Control UI",
    }


def _list_processes_alias(agent: WorkflowAgent, user_id: str) -> dict:
    """Deprecated alias — same data shaped as legacy list_processes."""
    result = _list_workflows(agent, user_id)
    return {
        "count": result["count"],
        "processes": [
            {
                "process_slug": w["slug"],
                "slug": w["slug"],
                "workflow_id": w["workflow_id"],
                "name": w["name"],
                "status": w["status"],
                "next_run": w["scheduled_at"],
            }
            for w in result["workflows"]
            if w.get("slug")
        ],
        "next_step": "prefer list_workflows; call get_workflow_status(slug=...)",
    }


register(
    name="list_workflows",
    fn=_list_workflows,
    description=(
        "List all workflows for the current user: slug, schedule, node count, last run."
    ),
    parameters={},
)

register(
    name="list_processes",
    fn=_list_processes_alias,
    description="Deprecated alias for list_workflows (named workflows only).",
    parameters={},
)
