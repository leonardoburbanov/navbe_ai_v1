from navbe_core.agent import WorkflowAgent
from navbe_destinations.duckdb import DESTINATION_TYPES

from navbe_mcp.registry import register


def _create_destination(
    agent: WorkflowAgent, user_id: str, type: str, name: str, config: dict = {}
) -> dict:
    if type not in DESTINATION_TYPES:
        return {
            "error": f"Unsupported destination type: {type!r}. Choose one of: {sorted(DESTINATION_TYPES)}"
        }

    destination = agent.repo.create_destination(
        user_id=user_id, type=type, name=name, config=config
    )
    return {"destination_id": destination.id, "type": destination.type, "name": destination.name}


def _list_destinations(agent: WorkflowAgent, user_id: str) -> dict:
    destinations = agent.repo.list_destinations(user_id)
    return {
        "count": len(destinations),
        "destinations": [
            {"destination_id": d.id, "type": d.type, "name": d.name} for d in destinations
        ],
    }


register(
    name="create_destination",
    fn=_create_destination,
    description=(
        "Register a destination (output) that workflow results get written to. "
        f"Supported types: {sorted(DESTINATION_TYPES)}. "
        "For 'csv_file', config may set 'folder' (defaults to the server's exports dir). "
        "For 'duckdb', config may set 'db_path' and 'table' (default 'traces')."
    ),
    parameters={
        "type": {"type": "string", "description": "Destination type: 'csv_file' or 'duckdb'"},
        "name": {"type": "string", "description": "A human-readable name for this destination"},
        "config": {
            "type": "object",
            "description": "Type-specific settings (folder, db_path, table)",
        },
    },
)

register(
    name="list_destinations",
    fn=_list_destinations,
    description="List all configured destinations (outputs) for the current user.",
    parameters={},
)
