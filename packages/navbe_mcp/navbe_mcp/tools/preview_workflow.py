"""MCP tool: preview_workflow — dry run without watermark advance."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent
from pydantic import BaseModel

from navbe_mcp.registry import register


class PreviewWorkflowResult(BaseModel):
    """Preview run response."""

    run_id: str | None = None
    status: str | None = None
    output: dict | None = None
    preview: bool = True
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
    return PreviewWorkflowResult(
        run_id=result.get("run_id"),
        status=result.get("status"),
        output=result.get("output"),
        preview=True,
        note="Watermark not advanced. Call run_workflow to execute for real.",
        next_step="call run_workflow(workflow_id) for a production run",
    ).model_dump()


register(
    name="preview_workflow",
    fn=_preview_workflow,
    description=(
        "Dry-run a workflow: extracts sample rows, writes to a preview sandbox, "
        "does not advance watermarks."
    ),
    parameters={"workflow_id": {"type": "string"}},
)
