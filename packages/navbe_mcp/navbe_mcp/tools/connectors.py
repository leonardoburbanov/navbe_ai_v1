"""MCP tools for source connectors and environments."""

from __future__ import annotations

from navbe_connectors.langfuse import DEFAULT_PAGE_SIZE, fetch_traces_page, test_langfuse_connection
from navbe_core.agent import WorkflowAgent
from navbe_core.live_url import connectors_ui_url

from navbe_mcp.registry import register


def _connector_payload(agent: WorkflowAgent, c) -> dict:
    return {
        "connector_id": c.id,
        "name": c.name,
        "type": c.type,
        "status": c.status,
        "host": c.host,
        "envs": agent.repo.env_summary(c.id),
        "ui_url": connectors_ui_url(tab="sources"),
    }


def _create_connector(
    agent: WorkflowAgent,
    user_id: str,
    name: str,
    host: str = "",
    public_key: str = "",
    secret_key: str = "",
    type: str = "langfuse",
    env_key: str = "prod",
) -> dict:
    connector = agent.repo.create_connector(
        user_id=user_id,
        name=name,
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        type=type,
        env_key=env_key,
    )
    return {
        **_connector_payload(agent, connector),
        "next_step": "call upsert_connector_env to add staging/testing, or set_workflow_source",
    }


def _list_connectors(agent: WorkflowAgent, user_id: str) -> dict:
    connectors = agent.repo.list_connectors(user_id)
    return {
        "count": len(connectors),
        "connectors": [_connector_payload(agent, c) for c in connectors],
        "next_step": "call get_connector or upsert_connector_env",
        "ui_url": connectors_ui_url(tab="sources"),
    }


def _get_connector(agent: WorkflowAgent, user_id: str, connector_id: str) -> dict:
    c = agent.repo.get_connector(connector_id, user_id)
    if c is None:
        return {"error": f"Connector not found: {connector_id}"}
    return _connector_payload(agent, c)


def _update_connector(
    agent: WorkflowAgent,
    user_id: str,
    connector_id: str,
    name: str | None = None,
    status: str | None = None,
) -> dict:
    c = agent.repo.update_connector(connector_id, user_id, name=name, status=status)
    if c is None:
        return {"error": f"Connector not found: {connector_id}"}
    return {**_connector_payload(agent, c), "next_step": "open ui_url"}


def _delete_connector(agent: WorkflowAgent, user_id: str, connector_id: str) -> dict:
    # Refuse if an active (non-archived) workflow references this connector
    for w in agent.repo.list_workflows(user_id):
        import json

        ctx = json.loads(w.context or "{}")
        inp = ctx.get("input") or {}
        if inp.get("connector_id") == connector_id or inp.get("connection_id") == connector_id:
            return {
                "error": f"Connector is used by workflow {w.id} ({w.name}); unbind first",
            }
        for nc in (ctx.get("graph") or {}).get("node_config") or {}.values():
            if isinstance(nc, dict) and nc.get("connector_id") == connector_id:
                return {
                    "error": f"Connector is used by workflow {w.id} step binding; clear first",
                }
    ok = agent.repo.delete_connector(connector_id, user_id)
    if not ok:
        return {"error": f"Connector not found: {connector_id}"}
    return {
        "deleted": True,
        "connector_id": connector_id,
        "ui_url": connectors_ui_url(tab="sources"),
        "next_step": "list_connectors",
    }


def _upsert_connector_env(
    agent: WorkflowAgent,
    user_id: str,
    connector_id: str,
    env_key: str,
    host: str | None = None,
    public_key: str | None = None,
    secret_key: str | None = None,
    public_config: dict | None = None,
    secrets: dict | None = None,
    is_default: bool = False,
    label: str | None = None,
) -> dict:
    pc = dict(public_config or {})
    if host:
        pc["host"] = host
    sec = dict(secrets or {})
    if public_key:
        sec["public_key"] = public_key
    if secret_key:
        sec["secret_key"] = secret_key
    try:
        row = agent.repo.upsert_connector_env(
            connector_id,
            user_id,
            env_key,
            public_config=pc,
            secrets=sec or None,
            is_default=is_default,
            label=label,
        )
    except ValueError as e:
        return {"error": str(e)}
    c = agent.repo.get_connector(connector_id, user_id)
    assert c is not None
    return {
        **_connector_payload(agent, c),
        "env_key": row.env_key,
        "next_step": "call test_connector to validate",
    }


def _delete_connector_env(
    agent: WorkflowAgent, user_id: str, connector_id: str, env_key: str
) -> dict:
    try:
        ok = agent.repo.delete_connector_env(connector_id, user_id, env_key)
    except ValueError as e:
        return {"error": str(e)}
    if not ok:
        return {"error": f"Environment {env_key!r} not found"}
    c = agent.repo.get_connector(connector_id, user_id)
    assert c is not None
    return {**_connector_payload(agent, c), "deleted_env": env_key}


def _test_connector(
    agent: WorkflowAgent,
    user_id: str,
    connector_id: str,
    env: str | None = None,
) -> dict:
    try:
        creds = agent.repo.resolve_connector_credentials(connector_id, user_id, env_key=env)
    except ValueError as e:
        return {"error": str(e)}
    try:
        probe = test_langfuse_connection(
            creds["host"], creds["public_key"], creds["secret_key"]
        )
    except Exception as e:
        probe = "error"
        err = str(e)
    else:
        err = None if probe == "connected" else f"probe={probe}"
    ok = probe == "connected"
    status = "ok" if ok else "error"
    env_row = agent.repo.get_connector_env(connector_id, env or creds.get("env_key"))
    if env_row:
        env_row.status = status
        agent.repo.db.commit()
    agent.repo.update_connector_status(connector_id, status if ok else "error")
    return {
        "connector_id": connector_id,
        "env_key": creds.get("env_key"),
        "status": status,
        "error": err,
        "ui_url": connectors_ui_url(tab="sources"),
        "next_step": "set_workflow_source" if ok else "fix credentials via upsert_connector_env",
    }


def _query_langfuse(
    agent: WorkflowAgent,
    user_id: str,
    connector_id: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    include_observations: bool = False,
    env: str | None = None,
) -> dict:
    try:
        creds = agent.repo.resolve_connector_credentials(connector_id, user_id, env_key=env)
    except ValueError as e:
        return {"error": str(e)}
    try:
        return fetch_traces_page(
            creds["host"],
            creds["public_key"],
            creds["secret_key"],
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
        "Register a source connector (e.g. Langfuse) with optional host/keys. "
        "Creates a prod environment pack. Prefer upsert_connector_env for staging/testing."
    ),
    parameters={
        "name": {"type": "string"},
        "host": {"type": "string"},
        "public_key": {"type": "string"},
        "secret_key": {"type": "string"},
        "type": {"type": "string"},
        "env_key": {"type": "string", "description": "Initial env key (default prod)"},
    },
)

register(
    name="list_connectors",
    fn=_list_connectors,
    description="List source connectors with environment summaries (secrets redacted).",
    parameters={},
)

register(
    name="get_connector",
    fn=_get_connector,
    description="Get one source connector with redacted environments.",
    parameters={"connector_id": {"type": "string"}},
)

register(
    name="update_connector",
    fn=_update_connector,
    description="Rename a connector or set status.",
    parameters={
        "connector_id": {"type": "string"},
        "name": {"type": "string"},
        "status": {"type": "string"},
    },
)

register(
    name="delete_connector",
    fn=_delete_connector,
    description="Delete a connector and its environments (refuses if a workflow still binds it).",
    parameters={"connector_id": {"type": "string"}},
)

register(
    name="upsert_connector_env",
    fn=_upsert_connector_env,
    description=(
        "Create or update a connector environment (staging/testing/prod/custom). "
        "Pass host/public_key/secret_key or public_config/secrets."
    ),
    parameters={
        "connector_id": {"type": "string"},
        "env_key": {"type": "string"},
        "host": {"type": "string"},
        "public_key": {"type": "string"},
        "secret_key": {"type": "string"},
        "public_config": {"type": "object"},
        "secrets": {"type": "object"},
        "is_default": {"type": "boolean"},
        "label": {"type": "string"},
    },
)

register(
    name="delete_connector_env",
    fn=_delete_connector_env,
    description="Delete one connector environment (not the last remaining).",
    parameters={
        "connector_id": {"type": "string"},
        "env_key": {"type": "string"},
    },
)

register(
    name="test_connector",
    fn=_test_connector,
    description="Probe a connector environment (default env if env omitted).",
    parameters={
        "connector_id": {"type": "string"},
        "env": {"type": "string"},
    },
)

register(
    name="query_langfuse",
    fn=_query_langfuse,
    description=(
        "Fetch one page of traces from Langfuse using a connector (+ optional env)."
    ),
    parameters={
        "connector_id": {"type": "string"},
        "page": {"type": "integer"},
        "page_size": {"type": "integer"},
        "include_observations": {"type": "boolean"},
        "env": {"type": "string"},
    },
)
