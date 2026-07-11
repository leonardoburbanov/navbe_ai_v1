"""Control UI deep links for live process watching."""

from __future__ import annotations

from navbe_core.config import settings


def live_process_url(
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
