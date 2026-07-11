"""MCP tool: get_process_status — shared live status for any agent."""

from __future__ import annotations

import json

from navbe_core.agent import WorkflowAgent
from pydantic import BaseModel

from navbe_mcp.registry import register


class ProcessStatusResult(BaseModel):
    """Shared process status visible to all agents."""

    found: bool
    process_slug: str
    workflow_id: str | None = None
    status: str | None = None
    next_run: str | None = None
    watermark: str | None = None
    last_run: dict | None = None
    next_step: str = ""


def _get_process_status(agent: WorkflowAgent, user_id: str, process_slug: str) -> dict:
    """Return live status for a named process (any subscribed agent)."""
    _ = user_id
    workflow = agent.repo.get_workflow_by_slug(process_slug)
    if workflow is None:
        return ProcessStatusResult(
            found=False,
            process_slug=process_slug,
            next_step="call list_processes to see all known processes",
        ).model_dump()

    last_run = agent.repo.get_last_run(workflow.id)
    last_run_payload = None
    if last_run is not None:
        last_run_payload = {
            "run_id": last_run.id,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat(),
            "completed_at": last_run.completed_at.isoformat() if last_run.completed_at else None,
            "output": json.loads(last_run.output) if last_run.output else None,
        }

    return ProcessStatusResult(
        found=True,
        process_slug=process_slug,
        workflow_id=workflow.id,
        status=workflow.status,
        next_run=workflow.scheduled_at.isoformat() if workflow.scheduled_at else None,
        watermark=workflow.watermark_at.isoformat() if workflow.watermark_at else None,
        last_run=last_run_payload,
        next_step="call pull_events after subscribe to watch live progress",
    ).model_dump()


register(
    name="get_process_status",
    fn=_get_process_status,
    description=(
        "Get the live status of a named process (workflow). Any agent can call this — "
        "it reads shared hub state."
    ),
    parameters={
        "process_slug": {
            "type": "string",
            "description": "Process name, e.g. 'langfuse_daily'",
        }
    },
)
