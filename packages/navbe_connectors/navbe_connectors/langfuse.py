from datetime import datetime, timedelta

import httpx

LANGFUSE_TIMEOUT_SECONDS = 30.0
LANGFUSE_OBSERVATION_TIMEOUT_SECONDS = 30.0
TRACES_LOOKBACK_HOURS = 24
TRACES_LIMIT = 50  # single page, capped — avoid pulling a connector's full trace history
DEFAULT_PAGE_SIZE = 10  # small enough to render as a table in a chat reply


def test_langfuse_connection(host: str, public_key: str, secret_key: str) -> str:
    """Ping a Langfuse instance with the given credentials.

    Returns "connected" if the keys are accepted, "error" otherwise
    (bad credentials, unreachable host, timeout).
    """
    try:
        response = httpx.get(
            f"{host.rstrip('/')}/api/public/projects",
            auth=(public_key, secret_key),
            timeout=LANGFUSE_TIMEOUT_SECONDS,
        )
        return "connected" if response.status_code == 200 else "error"
    except httpx.HTTPError:
        return "error"


def _fetch_traces(
    host: str, public_key: str, secret_key: str, limit: int, since: datetime | None
) -> list[dict]:
    """One bounded request to Langfuse's traces API — always capped at
    `limit` and never paginated, to keep this cheap against Langfuse's
    usage-based API.
    """
    params = {"limit": limit, "orderBy": "timestamp.desc"}
    if since is not None:
        params["fromTimestamp"] = since.isoformat() + "Z"

    response = httpx.get(
        f"{host.rstrip('/')}/api/public/traces",
        params=params,
        auth=(public_key, secret_key),
        timeout=LANGFUSE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json().get("data", [])
    return [
        {
            "id": trace.get("id"),
            "name": trace.get("name"),
            "timestamp": trace.get("timestamp"),
            "userId": trace.get("userId"),
        }
        for trace in data
    ]


def fetch_recent_traces(host: str, public_key: str, secret_key: str) -> list[dict]:
    """Fetch up to the last `TRACES_LIMIT` traces from the last
    `TRACES_LOOKBACK_HOURS` hours.
    """
    since = datetime.utcnow() - timedelta(hours=TRACES_LOOKBACK_HOURS)
    return _fetch_traces(host, public_key, secret_key, limit=TRACES_LIMIT, since=since)


def fetch_last_traces(
    host: str, public_key: str, secret_key: str, limit: int = 50, include_observations: bool = False
) -> list[dict]:
    """Fetch the most recent `limit` traces, regardless of age."""
    traces = _fetch_traces(host, public_key, secret_key, limit=limit, since=None)
    if include_observations:
        for trace in traces:
            try:
                trace["observations"] = fetch_observations(
                    host, public_key, secret_key, trace["id"]
                )
            except httpx.HTTPError:
                trace["observations"] = []
    return traces


def fetch_observations(
    host: str, public_key: str, secret_key: str, trace_id: str, limit: int = 100
) -> list[dict]:
    """Fetch the observations (spans/generations/events) belonging to one trace."""
    response = httpx.get(
        f"{host.rstrip('/')}/api/public/observations",
        params={"traceId": trace_id, "limit": limit},
        auth=(public_key, secret_key),
        timeout=LANGFUSE_OBSERVATION_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return [
        {
            "id": o.get("id"),
            "type": o.get("type"),
            "name": o.get("name"),
            "startTime": o.get("startTime"),
            "endTime": o.get("endTime"),
        }
        for o in response.json().get("data", [])
    ]


def fetch_traces_page(
    host: str,
    public_key: str,
    secret_key: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    include_observations: bool = False,
) -> dict:
    """Fetch one page of traces straight from Langfuse, using its own
    `page`/`limit` pagination (unlike `fetch_recent_traces`/`fetch_last_traces`,
    which are bounded single-page fetches for the export workflow).

    ponytail: Langfuse's API has no "observations for these N traces" batch
    endpoint, so include_observations does one extra request per trace —
    fine at the default page_size of 10, keep page_size small if enabling it.
    """
    response = httpx.get(
        f"{host.rstrip('/')}/api/public/traces",
        params={"page": page, "limit": page_size, "orderBy": "timestamp.desc"},
        auth=(public_key, secret_key),
        timeout=LANGFUSE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    meta = payload.get("meta", {})

    traces = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "timestamp": t.get("timestamp"),
            "userId": t.get("userId"),
        }
        for t in payload.get("data", [])
    ]
    if include_observations:
        for trace in traces:
            trace["observations"] = fetch_observations(host, public_key, secret_key, trace["id"])

    return {
        "traces": traces,
        "page": meta.get("page", page),
        "page_size": meta.get("limit", page_size),
        "total": meta.get("totalItems", len(traces)),
    }
