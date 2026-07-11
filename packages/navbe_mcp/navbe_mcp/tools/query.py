import json

from navbe_core.agent import WorkflowAgent
from navbe_core.query import DEFAULT_PAGE_SIZE, describe_destination, query_destination

from navbe_mcp.registry import register


def _get_destination_or_error(agent: WorkflowAgent, user_id: str, destination_id: str):
    destination = agent.repo.get_destination(destination_id, user_id)
    if destination is None:
        return None, {"error": f"Destination not found: {destination_id}"}
    return destination, None


def _describe_destination(agent: WorkflowAgent, user_id: str, destination_id: str) -> dict:
    destination, error = _get_destination_or_error(agent, user_id, destination_id)
    if error:
        return error
    try:
        return describe_destination(destination.type, json.loads(destination.config))
    except Exception as e:
        return {"error": str(e)}


def _query_destination(
    agent: WorkflowAgent,
    user_id: str,
    destination_id: str,
    sql: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    destination, error = _get_destination_or_error(agent, user_id, destination_id)
    if error:
        return error
    try:
        return query_destination(
            destination.type, json.loads(destination.config), sql, page=page, page_size=page_size
        )
    except Exception as e:
        return {"error": str(e)}


def _query_workflow_destination(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str,
    sql: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    try:
        return agent.query_workflow_destination(
            workflow_id, user_id, sql, page=page, page_size=page_size
        )
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


register(
    name="describe_destination",
    fn=_describe_destination,
    description=(
        "Show the column names and types available on a destination, exposed as a "
        "table called `traces` regardless of whether it's backed by csv_file or duckdb. "
        "Call this before query_destination if you don't already know the schema."
    ),
    parameters={
        "destination_id": {"type": "string", "description": "ID of the destination to inspect"},
    },
)

register(
    name="query_destination",
    fn=_query_destination,
    description=(
        "Run a read-only SQL SELECT against a destination's data (table name is "
        "always `traces`). Works for both csv_file and duckdb destinations. "
        "Paginated, defaulting to 10 rows per page so results read well in a chat reply."
    ),
    parameters={
        "destination_id": {"type": "string", "description": "ID of the destination to query"},
        "sql": {
            "type": "string",
            "description": "A SELECT statement, e.g. SELECT * FROM traces ORDER BY timestamp",
        },
        "page": {"type": "integer", "description": "1-indexed page number (default 1)"},
        "page_size": {"type": "integer", "description": "Rows per page, max 200 (default 10)"},
    },
)

register(
    name="query_workflow_destination",
    fn=_query_workflow_destination,
    description=(
        "Run a read-only SQL SELECT against the Langfuse data a workflow exports (table is "
        "always `traces`). Only the workflow_id is needed — its destination (duckdb or "
        "csv_file) is resolved automatically from the workflow's own context. "
        "Trace columns are stored as text, so cast timestamp before using date functions. "
        "Paginated, defaulting to 10 rows per page so results read well in a chat reply. "
        "Example — trace count per hour today: "
        "SELECT strftime(CAST(timestamp AS TIMESTAMP), '%H') AS hour, count(*) AS traces "
        "FROM traces WHERE CAST(timestamp AS TIMESTAMP) >= current_date "
        "GROUP BY hour ORDER BY hour"
    ),
    parameters={
        "workflow_id": {
            "type": "string",
            "description": "ID of the workflow whose destination to query",
        },
        "sql": {"type": "string", "description": "A SELECT statement against the `traces` table"},
        "page": {"type": "integer", "description": "1-indexed page number (default 1)"},
        "page_size": {"type": "integer", "description": "Rows per page, max 200 (default 10)"},
    },
)
