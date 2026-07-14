"""Control UI deep links for live workflow watching."""

from __future__ import annotations

from navbe_core.config import settings


def live_workflow_url(
    *,
    workflow_id: str,
    run_id: str | None = None,
    page: str = "runs",
) -> str:
    """Absolute Control UI deep link for a live (or just-started) run."""
    q = f"page={page}&workflow={workflow_id}"
    if run_id:
        q += f"&run={run_id}"
    return f"{settings.UI_URL.rstrip('/')}/?{q}"


def connectors_ui_url(*, tab: str = "sources", type: str | None = None) -> str:
    """Deep link to the Connectors hub."""
    q = f"page=connectors&tab={tab}"
    if type:
        q += f"&type={type}"
    return f"{settings.UI_URL.rstrip('/')}/?{q}"


def workflow_ui_url(*, workflow_id: str) -> str:
    """Deep link to the Workflows page detail for a definition."""
    return live_workflow_url(workflow_id=workflow_id, page="workflows")


# ponytail: alias for one sprint — callers migrate to live_workflow_url
live_process_url = live_workflow_url
