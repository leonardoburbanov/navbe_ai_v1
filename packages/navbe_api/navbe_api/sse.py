"""SSE helpers for live run event streams."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from navbe_notify import bus as events


def stream_workflow_events(workflow_id: str) -> StreamingResponse:
    """Return an SSE StreamingResponse filtered to one workflow_id."""

    async def event_stream() -> AsyncIterator[str]:
        queue = events.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event.get("workflow_id") == workflow_id:
                    yield f"data: {json.dumps(event)}\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stream_all_events() -> StreamingResponse:
    """Return an SSE StreamingResponse of all hub events (Control UI)."""

    async def event_stream() -> AsyncIterator[str]:
        queue = events.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
