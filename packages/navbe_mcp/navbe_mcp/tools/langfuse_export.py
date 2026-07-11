from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _create_langfuse_export_workflow(
    agent: WorkflowAgent,
    user_id: str,
    name: str,
    connector_id: str,
    destination_id: str,
    when: str = "+5s",
    include_observations: bool = False,
    process_slug: str = "langfuse_daily",
) -> dict:
    workflow = agent.create_langfuse_export_workflow(
        user_id=user_id,
        name=name,
        connector_id=connector_id,
        destination_id=destination_id,
        when=when,
        include_observations=include_observations,
        process_slug=process_slug,
    )
    return {
        "workflow_id": workflow.id,
        "name": workflow.name,
        "process_slug": workflow.process_slug,
        "scheduled_at": workflow.scheduled_at.isoformat(),
        "message": f"Scheduled '{name}' for {workflow.scheduled_at.strftime('%A %b %d at %I:%M %p')} UTC",
    }


register(
    name="create_langfuse_export_workflow",
    fn=_create_langfuse_export_workflow,
    description=(
        "Schedule a workflow that fetches traces from a Langfuse connector "
        "and writes them to a destination. Set include_observations=true to also fetch "
        "and store each trace's observations (spans/generations/events) in DuckDB "
        "(exports 10 traces when observations are enabled, 50 otherwise). "
        "Requires an existing connector_id (see create_connector/list_connectors) and "
        "destination_id (see create_destination/list_destinations)."
    ),
    parameters={
        "name": {"type": "string", "description": "Workflow name"},
        "connector_id": {
            "type": "string",
            "description": "ID of the Langfuse connector to read from",
        },
        "destination_id": {"type": "string", "description": "ID of the destination to write to"},
        "when": {
            "type": "string",
            "description": "When to run: +30s, +1m, +1h, 'monday 9am', or a cron expression. Defaults to +5s.",
        },
        "include_observations": {
            "type": "boolean",
            "description": "Also fetch and export each trace's observations (DuckDB only, default false)",
        },
        "process_slug": {
            "type": "string",
            "description": "Friendly process name for status queries (default langfuse_daily)",
        },
    },
)
