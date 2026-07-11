"""MCP tool: preview_workflow — dry run without watermark advance."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent
from pydantic import BaseModel

from navbe_mcp.registry import register


class PreviewWorkflowResult(BaseModel):
    """Preview run response."""

    run_id: str | None = None
    workflow_id: str | None = None
    status: str | None = None
    output: dict | None = None
    preview: bool = True
    live_url: str | None = None
    note: str = ""
    error: str | None = None
    next_step: str = ""


def _preview_workflow(agent: WorkflowAgent, user_id: str, workflow_id: str) -> dict:
    """Dry-run a workflow into a preview sandbox; do not advance watermarks."""
    workflow = agent.repo.get_workflow(workflow_id, user_id)
    if workflow is None:
        return PreviewWorkflowResult(
            error=f"Workflow not found: {workflow_id}",
            next_step="call list_workflows or list_processes",
        ).model_dump()

    result = agent.run_now(workflow_id, user_id, mode="preview")
    live_url = result.get("live_url")
    return PreviewWorkflowResult(
        run_id=result.get("run_id"),
        workflow_id=workflow_id,
        status=result.get("status"),
        output=result.get("output"),
        preview=True,
        live_url=live_url,
        note="Watermark not advanced. Call run_workflow to execute for real.",
        next_step=(
            f"Open live_url to review the DAG: {live_url}"
            if live_url
            else "call run_workflow(workflow_id) for a production run"
        ),
    ).model_dump()


register(
    name="preview_workflow",
    fn=_preview_workflow,
    description=(
        "Dry-run a workflow: extracts sample rows, writes to a preview sandbox, "
        "does not advance watermarks. Returns live_url for the Control UI DAG."
    ),
    parameters={"workflow_id": {"type": "string"}},
)
