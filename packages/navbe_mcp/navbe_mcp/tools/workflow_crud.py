"""MCP tools: update / delete / trigger / source / dest / step mutators."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _update_workflow(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    name: str | None = None,
    slug: str | None = None,
    task: str | None = None,
    status: str | None = None,
) -> dict:
    return agent.update_workflow(
        user_id, workflow_id, name=name, slug=slug, task=task, status=status
    )


def _delete_workflow(agent: WorkflowAgent, user_id: str, workflow_id: str) -> dict:
    return agent.delete_workflow(user_id, workflow_id)


def _set_workflow_trigger(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    when: str | None = None,
    hint: str | None = None,
) -> dict:
    return agent.set_workflow_trigger(user_id, workflow_id, when=when, hint=hint)


def _set_workflow_source(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    connector_id: str,
    connector_env: str | None = None,
) -> dict:
    return agent.set_workflow_source(
        user_id, workflow_id, connector_id, connector_env=connector_env
    )


def _set_workflow_step_connector(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    step: str,
    connector_id: str | None = None,
    env: str | None = None,
    config: dict | None = None,
    clear: bool = False,
) -> dict:
    return agent.set_workflow_step_connector(
        user_id,
        workflow_id,
        step,
        connector_id=connector_id,
        env=env,
        config=config,
        clear=clear,
    )


def _set_workflow_destination(
    agent: WorkflowAgent, user_id: str, workflow_id: str, destination_id: str
) -> dict:
    return agent.set_workflow_destination(user_id, workflow_id, destination_id)


def _add_workflow_step(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    step: str | None = None,
    hint: str | None = None,
) -> dict:
    return agent.add_workflow_step(user_id, workflow_id, step=step, hint=hint)


def _remove_workflow_step(
    agent: WorkflowAgent, user_id: str, workflow_id: str, step: str
) -> dict:
    return agent.remove_workflow_step(user_id, workflow_id, step)


def _connect_workflow_steps(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    source: str,
    target: str,
) -> dict:
    return agent.connect_workflow_steps(user_id, workflow_id, source, target)


register(
    name="update_workflow",
    fn=_update_workflow,
    description="Patch workflow name, slug, task description, or status.",
    parameters={
        "workflow_id": {"type": "string"},
        "name": {"type": "string"},
        "slug": {"type": "string"},
        "task": {"type": "string"},
        "status": {"type": "string", "description": "e.g. scheduled, paused"},
    },
)

register(
    name="delete_workflow",
    fn=_delete_workflow,
    description="Soft-archive a workflow (status=archived). Refuses if a run is in progress.",
    parameters={"workflow_id": {"type": "string"}},
)

register(
    name="set_workflow_trigger",
    fn=_set_workflow_trigger,
    description=(
        "Set workflow trigger: cron expression, relative time, or 'manual'. "
        "Accepts when= or free-text hint=."
    ),
    parameters={
        "workflow_id": {"type": "string"},
        "when": {"type": "string"},
        "hint": {"type": "string"},
    },
)

register(
    name="set_workflow_source",
    fn=_set_workflow_source,
    description=(
        "Bind a source connector to the workflow (input.connector_id). "
        "Optional connector_env selects staging/testing/prod."
    ),
    parameters={
        "workflow_id": {"type": "string"},
        "connector_id": {"type": "string"},
        "connector_env": {"type": "string"},
    },
)

register(
    name="set_workflow_step_connector",
    fn=_set_workflow_step_connector,
    description=(
        "Set or clear graph.node_config[step] for per-step connector/env/config. "
        "Pass clear=true to remove the override."
    ),
    parameters={
        "workflow_id": {"type": "string"},
        "step": {"type": "string"},
        "connector_id": {"type": "string"},
        "env": {"type": "string"},
        "config": {"type": "object"},
        "clear": {"type": "boolean"},
    },
)

register(
    name="set_workflow_destination",
    fn=_set_workflow_destination,
    description="Bind a destination to the workflow IR input.destination_id.",
    parameters={
        "workflow_id": {"type": "string"},
        "destination_id": {"type": "string"},
    },
)

register(
    name="add_workflow_step",
    fn=_add_workflow_step,
    description=(
        "Append a registered step and auto-wire edges when unambiguous. "
        "Pass step= id or hint= natural language (e.g. 'refresh the retailer mart')."
    ),
    parameters={
        "workflow_id": {"type": "string"},
        "step": {"type": "string"},
        "hint": {"type": "string"},
    },
)

register(
    name="remove_workflow_step",
    fn=_remove_workflow_step,
    description="Remove a step and its incident edges; recomputes entry.",
    parameters={
        "workflow_id": {"type": "string"},
        "step": {"type": "string"},
    },
)

register(
    name="connect_workflow_steps",
    fn=_connect_workflow_steps,
    description="Explicitly add an edge between two existing steps.",
    parameters={
        "workflow_id": {"type": "string"},
        "source": {"type": "string"},
        "target": {"type": "string"},
    },
)
