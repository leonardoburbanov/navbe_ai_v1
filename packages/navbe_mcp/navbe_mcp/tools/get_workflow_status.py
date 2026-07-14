"""MCP tool: get_workflow_status — shared live status (canonical Sprint 9 name)."""

from __future__ import annotations

import json

from navbe_core.agent import WorkflowAgent, _workflow_slug
from navbe_core.live_url import live_workflow_url, workflow_ui_url
from pydantic import BaseModel

from navbe_mcp.registry import register


class WorkflowStatusResult(BaseModel):
    """Shared workflow status visible to all agents."""

    found: bool
    slug: str | None = None
    process_slug: str | None = None  # dual key one sprint
    workflow_id: str | None = None
    status: str | None = None
    next_run: str | None = None
    watermark: str | None = None
    last_run: dict | None = None
    live_url: str | None = None
    ui_url: str | None = None
    next_step: str = ""


def _get_workflow_status(
    agent: WorkflowAgent,
    user_id: str,
    slug: str | None = None,
    process_slug: str | None = None,
    workflow_id: str | None = None,
) -> dict:
    """Return live status by slug or workflow_id."""
    _ = user_id
    key = slug or process_slug
    workflow = None
    if workflow_id:
        workflow = agent.repo.get_workflow(workflow_id, user_id=None)
    elif key:
        workflow = agent.repo.get_workflow_by_slug(key)
    else:
        return WorkflowStatusResult(
            found=False,
            next_step="pass slug= or workflow_id=",
        ).model_dump()

    display = key or (workflow_id or "")
    if workflow is None:
        return WorkflowStatusResult(
            found=False,
            slug=key,
            process_slug=key,
            next_step="call list_workflows to see all known workflows",
        ).model_dump()

    friendly = _workflow_slug(workflow) or display
    last_run = agent.repo.get_last_run(workflow.id)
    last_run_payload = None
    live_url = None
    ui_url = workflow_ui_url(workflow_id=workflow.id)
    if last_run is not None:
        last_run_payload = {
            "run_id": last_run.id,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat(),
            "completed_at": last_run.completed_at.isoformat() if last_run.completed_at else None,
            "output": json.loads(last_run.output) if last_run.output else None,
        }
        live_url = live_workflow_url(workflow_id=workflow.id, run_id=last_run.id)
        if last_run.status == "running":
            next_step = f"Open live_url to watch the run live: {live_url}"
        else:
            next_step = f"Open ui_url for the workflow: {ui_url}"
    else:
        live_url = live_workflow_url(workflow_id=workflow.id)
        next_step = f"Open ui_url for the workflow: {ui_url}"

    return WorkflowStatusResult(
        found=True,
        slug=friendly,
        process_slug=friendly,
        workflow_id=workflow.id,
        status=workflow.status,
        next_run=workflow.scheduled_at.isoformat() if workflow.scheduled_at else None,
        watermark=workflow.watermark_at.isoformat() if workflow.watermark_at else None,
        last_run=last_run_payload,
        live_url=live_url,
        ui_url=ui_url,
        next_step=next_step,
    ).model_dump()


def _get_process_status_alias(
    agent: WorkflowAgent, user_id: str, process_slug: str
) -> dict:
    """Deprecated alias → get_workflow_status."""
    return _get_workflow_status(agent, user_id, slug=process_slug, process_slug=process_slug)


register(
    name="get_workflow_status",
    fn=_get_workflow_status,
    description=(
        "Get the live status of a workflow by slug or workflow_id. "
        "Any agent can call this — it reads shared hub state."
    ),
    parameters={
        "slug": {"type": "string", "description": "Friendly workflow slug, e.g. langfuse_daily"},
        "process_slug": {
            "type": "string",
            "description": "Deprecated alias for slug",
        },
        "workflow_id": {"type": "string", "description": "Workflow UUID"},
    },
)

register(
    name="get_process_status",
    fn=_get_process_status_alias,
    description=(
        "Deprecated alias for get_workflow_status. Prefer get_workflow_status(slug=...)."
    ),
    parameters={
        "process_slug": {
            "type": "string",
            "description": "Workflow slug (legacy process name)",
        }
    },
)
