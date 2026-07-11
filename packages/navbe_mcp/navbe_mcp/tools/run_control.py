"""MCP tools: pause_run / resume_run / stop_run."""

from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _pause_run(agent: WorkflowAgent, user_id: str, run_id: str) -> dict:
    del user_id  # ownership checked via run existence on local hub
    return agent.pause_run(run_id)


def _resume_run(agent: WorkflowAgent, user_id: str, run_id: str) -> dict:
    return agent.resume_paused_run(run_id, user_id)


def _stop_run(agent: WorkflowAgent, user_id: str, run_id: str) -> dict:
    del user_id
    return agent.stop_run(run_id)


register(
    name="pause_run",
    fn=_pause_run,
    description=(
        "Soft-pause a running workflow after the current LangGraph step finishes. "
        "Returns live_url for the Control UI Runs sheet."
    ),
    parameters={
        "run_id": {"type": "string", "description": "The run ID to pause"},
    },
)

register(
    name="resume_run",
    fn=_resume_run,
    description=(
        "Resume a paused run (re-enters the graph; sync steps are idempotent). "
        "Returns live_url for the Control UI Runs sheet."
    ),
    parameters={
        "run_id": {"type": "string", "description": "The paused run ID to resume"},
    },
)

register(
    name="stop_run",
    fn=_stop_run,
    description=(
        "Cancel a running or paused run after the current step (or immediately if paused). "
        "Returns live_url for the Control UI Runs sheet."
    ),
    parameters={
        "run_id": {"type": "string", "description": "The run ID to stop"},
    },
)
