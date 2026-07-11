from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _run_workflow(
    agent: WorkflowAgent, user_id: str, workflow_id: str, mode: str = "append"
) -> dict:
    return agent.run_now(workflow_id, user_id, mode=mode)


register(
    name="run_workflow",
    fn=_run_workflow,
    description=(
        "Run a workflow immediately instead of waiting for its schedule. "
        "mode='append' (default) writes new traces without duplicating ones already at the "
        "destination; mode='overwrite' replaces the destination's existing data. "
        "Returns live_url to open the Control UI Runs sheet while/after the run."
    ),
    parameters={
        "workflow_id": {"type": "string", "description": "The workflow ID to run"},
        "mode": {
            "type": "string",
            "description": "'append' (default, skip duplicates) or 'overwrite' (replace existing data)",
        },
    },
)
