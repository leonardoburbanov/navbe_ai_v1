from navbe_connectors.langfuse import DEFAULT_PAGE_SIZE, fetch_traces_page
from navbe_core.agent import WorkflowAgent

from navbe_mcp.registry import register


def _create_connector(
    agent: WorkflowAgent, user_id: str, name: str, host: str, public_key: str, secret_key: str
) -> dict:
    connector = agent.repo.create_connector(
        user_id=user_id, name=name, host=host, public_key=public_key, secret_key=secret_key
    )
    return {
        "connector_id": connector.id,
        "name": connector.name,
        "host": connector.host,
        "status": connector.status,
    }


def _list_connectors(agent: WorkflowAgent, user_id: str) -> dict:
    connectors = agent.repo.list_connectors(user_id)
    return {
        "count": len(connectors),
        "connectors": [
            {"connector_id": c.id, "name": c.name, "host": c.host, "status": c.status}
            for c in connectors
        ],
    }


def _query_langfuse(
    agent: WorkflowAgent,
    user_id: str,
    connector_id: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    include_observations: bool = False,
) -> dict:
    connector = agent.repo.get_connector(connector_id, user_id)
    if connector is None:
        return {"error": f"Connector not found: {connector_id}"}
    try:
        return fetch_traces_page(
            connector.host,
            connector.public_key,
            connector.secret_key,
            page=page,
            page_size=page_size,
            include_observations=include_observations,
        )
    except Exception as e:
        return {"error": str(e)}


register(
    name="create_connector",
    fn=_create_connector,
    description=(
        "Register a Langfuse connector (input source) with its host and API keys, "
        "so workflows can pull traces from it. Returns the new connector_id."
    ),
    parameters={
        "name": {"type": "string", "description": "A human-readable name for this connection"},
        "host": {"type": "string", "description": "Langfuse host, e.g. https://cloud.langfuse.com"},
        "public_key": {"type": "string", "description": "Langfuse public key (pk-lf-...)"},
        "secret_key": {"type": "string", "description": "Langfuse secret key (sk-lf-...)"},
    },
)

register(
    name="list_connectors",
    fn=_list_connectors,
    description="List all configured Langfuse connectors (input sources) for the current user.",
    parameters={},
)

register(
    name="query_langfuse",
    fn=_query_langfuse,
    description=(
        "Fetch one page of traces directly from Langfuse (the source), using Langfuse's own "
        "page/limit pagination — unlike the export workflow's single bounded fetch. "
        "Set include_observations=true to attach each trace's observations (spans/generations/"
        "events); this costs one extra request per trace, so keep page_size small when enabled."
    ),
    parameters={
        "connector_id": {"type": "string", "description": "ID of the Langfuse connector to query"},
        "page": {"type": "integer", "description": "1-indexed page number (default 1)"},
        "page_size": {"type": "integer", "description": "Traces per page (default 10)"},
        "include_observations": {
            "type": "boolean",
            "description": "Attach each trace's observations (default false)",
        },
    },
)
