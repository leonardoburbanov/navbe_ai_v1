"""MCP tool: list_processes — named processes on the hub."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent
from pydantic import BaseModel, Field

from navbe_mcp.registry import register


class ListProcessesResult(BaseModel):
    """List of named processes."""

    processes: list[dict] = Field(default_factory=list)
    next_step: str


def _list_processes(agent: WorkflowAgent, user_id: str) -> dict:
    """List all named processes visible to agents on this hub."""
    workflows = agent.repo.list_workflows_with_slug(user_id)
    return ListProcessesResult(
        processes=[
            {
                "process_slug": w.process_slug,
                "workflow_id": w.id,
                "status": w.status,
                "scheduled_at": w.scheduled_at.isoformat() if w.scheduled_at else None,
            }
            for w in workflows
        ],
        next_step="call get_process_status(process_slug) for details on any process",
    ).model_dump()


register(
    name="list_processes",
    fn=_list_processes,
    description="List all named processes visible to all agents on this hub.",
    parameters={},
)
