"""MCP tool: pull_events from the durable bus."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent
from navbe_notify import bus
from pydantic import BaseModel, Field

from navbe_mcp.registry import register


class PullEventsResult(BaseModel):
    """Response for pull_events."""

    events: list[dict] = Field(default_factory=list)
    count: int
    next_step: str


def _pull_events(agent: WorkflowAgent, user_id: str, subscriber_id: str, limit: int = 50) -> dict:
    """Poll events since this subscriber's cursor and advance it."""
    _ = agent, user_id
    events = bus.pull(subscriber_id, limit=limit)
    return PullEventsResult(
        events=events,
        count=len(events),
        next_step=(
            "call pull_events again to poll for new events"
            if events
            else "no new events since last poll"
        ),
    ).model_dump()


register(
    name="pull_events",
    fn=_pull_events,
    description=(
        "Poll the event bus for events since this subscriber's last cursor. "
        "Returns up to limit events and advances the cursor."
    ),
    parameters={
        "subscriber_id": {"type": "string"},
        "limit": {
            "type": "integer",
            "description": "Max events to return (default 50)",
        },
    },
)
