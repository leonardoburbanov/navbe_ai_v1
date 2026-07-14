"""MCP tool: subscribe to the event bus."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent
from navbe_notify import bus
from pydantic import BaseModel, Field

from navbe_mcp.registry import register


class SubscribeResult(BaseModel):
    """Response for subscribe."""

    subscriber_id: str
    registered: bool
    topics: list[str] = Field(default_factory=list)
    next_step: str


def _subscribe(
    agent: WorkflowAgent,
    user_id: str,
    subscriber_id: str,
    topics: list[str] | None = None,
) -> dict:
    """Register as a named subscriber; then poll with pull_events."""
    _ = agent, user_id
    bus.register_subscriber(subscriber_id)
    topic_list = topics or ["workflow.*", "process.*", "run.*"]
    return SubscribeResult(
        subscriber_id=subscriber_id,
        registered=True,
        topics=topic_list,
        next_step=(
            "call pull_events(subscriber_id) to receive events since this cursor; "
            "terminal run events include agent_message with the result summary"
        ),
    ).model_dump()


register(
    name="subscribe",
    fn=_subscribe,
    description=(
        "Register as a named subscriber to the event bus. Call once per agent session, "
        "then poll with pull_events. Independent cursors per subscriber_id. "
        "Use subscriber_id='cursor' from Cursor. Terminal runs include agent_message."
    ),
    parameters={
        "subscriber_id": {
            "type": "string",
            "description": "Stable ID for this agent, e.g. 'cursor', 'claude', 'hermes'",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Topic patterns to watch, e.g. ['workflow.*', 'process.*', 'run.*']",
        },
    },
)
