"""In-process pub/sub for workflow run events (Sprint 0 stub).

Broadcast over SSE. One queue per connected client; publish() is safe to call
from any thread (the scheduler fires workflows in a worker thread).

ponytail: in-memory only, single-process — Sprint 1 upgrades to SQLite
append-only events + subscriber cursors.
"""

from __future__ import annotations

import asyncio

_subscribers: set[asyncio.Queue] = set()
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Bind the running event loop so publish() can fan out from worker threads."""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    """Register a live SSE client queue."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    """Remove a live SSE client queue."""
    _subscribers.discard(queue)


def publish(event: dict) -> None:
    """Fan-out an event dict to all live subscribers (no persistence yet)."""
    if _loop is None:
        return
    for queue in list(_subscribers):
        _loop.call_soon_threadsafe(queue.put_nowait, event)
