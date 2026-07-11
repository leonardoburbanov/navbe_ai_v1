# Sprint 1 — Durable Event Bus + Multi-Agent MCP Tools

Upgrade the in-memory `events.py` to a SQLite-backed append-only bus with per-subscriber cursors. Add the five MCP tools that enable multi-agent status sharing.

## Goal

Two separate MCP clients (Cursor + any other agent) can both call `get_process_status("langfuse_daily")` and `pull_events` and see the same data, even if one connected after the event was published.

## navbe_notify/bus.py — full replacement

```python
import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

# ponytail: single SQLite file for events; swap for NATS if multi-process needed
_DB: Optional[Path] = None
_subscribers: set[asyncio.Queue] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None


def init(db_path: Path) -> None:
    """Call once at daemon startup."""
    global _DB
    _DB = db_path
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            topic     TEXT NOT NULL,
            type      TEXT NOT NULL,
            payload   TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS subscriber_cursors (
            subscriber_id TEXT PRIMARY KEY,
            last_event_id INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT NOT NULL
        );
    """)
    con.close()


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe_queue() -> asyncio.Queue:
    """Register an SSE client queue (live fan-out only)."""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    return q


def unsubscribe_queue(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(topic: str, type_: str, payload: dict) -> int:
    """Persist event; fan-out to live SSE queues. Returns event id."""
    assert _DB is not None, "bus.init() not called"
    ts = datetime.now(UTC).isoformat()
    con = sqlite3.connect(_DB)
    cur = con.execute(
        "INSERT INTO events(ts, topic, type, payload) VALUES (?,?,?,?)",
        (ts, topic, type_, json.dumps(payload)),
    )
    event_id = cur.lastrowid
    con.commit()
    con.close()

    event = {"id": event_id, "ts": ts, "topic": topic, "type": type_, **payload}
    if _loop is not None:
        for q in list(_subscribers):
            _loop.call_soon_threadsafe(q.put_nowait, event)
    return event_id


def register_subscriber(subscriber_id: str) -> None:
    assert _DB is not None
    con = sqlite3.connect(_DB)
    con.execute(
        """INSERT INTO subscriber_cursors(subscriber_id, last_event_id, updated_at)
           VALUES (?,0,?) ON CONFLICT(subscriber_id) DO NOTHING""",
        (subscriber_id, datetime.now(UTC).isoformat()),
    )
    con.commit()
    con.close()


def pull(subscriber_id: str, limit: int = 50) -> list[dict]:
    """Return up to `limit` events after this subscriber's cursor; advance cursor."""
    assert _DB is not None
    con = sqlite3.connect(_DB)
    con.row_factory = sqlite3.Row
    cursor_row = con.execute(
        "SELECT last_event_id FROM subscriber_cursors WHERE subscriber_id=?",
        (subscriber_id,),
    ).fetchone()
    last_id = cursor_row["last_event_id"] if cursor_row else 0

    rows = con.execute(
        "SELECT id,ts,topic,type,payload FROM events WHERE id>? ORDER BY id LIMIT ?",
        (last_id, limit),
    ).fetchall()

    if rows:
        new_last = rows[-1]["id"]
        con.execute(
            "UPDATE subscriber_cursors SET last_event_id=?, updated_at=? WHERE subscriber_id=?",
            (new_last, datetime.now(UTC).isoformat(), subscriber_id),
        )
        con.commit()
    con.close()

    return [
        {"id": r["id"], "ts": r["ts"], "topic": r["topic"],
         "type": r["type"], **json.loads(r["payload"])}
        for r in rows
    ]
```

## Publish helper for agent.py

Replace bare `events.publish({...})` calls in `agent.py` with:

```python
from navbe_notify import bus

# on run start:
bus.publish(f"run.{run.id}", "run.started",
            {"workflow_id": workflow_id, "run_id": run.id, "process_slug": workflow.process_slug})

# on step complete:
bus.publish(f"run.{run_id}", "run.step",
            {"step": step_name, "workflow_id": workflow_id})

# on completion:
bus.publish(f"process.{workflow.process_slug}", "run.succeeded",
            {"workflow_id": workflow_id, "run_id": run.id, "output": output})

# on failure:
bus.publish(f"process.{workflow.process_slug}", "run.failed",
            {"workflow_id": workflow_id, "run_id": run.id, "error": str(e)})
```

## New MCP tools (add to navbe_mcp/tools/)

### subscribe.py

```python
from navbe_notify import bus
from navbe_mcp.registry import register
from pydantic import BaseModel

class SubscribeResult(BaseModel):
    subscriber_id: str
    registered: bool
    next_step: str

def _subscribe(agent, user_id: str, subscriber_id: str, topics: list[str]) -> dict:
    bus.register_subscriber(subscriber_id)
    return SubscribeResult(
        subscriber_id=subscriber_id,
        registered=True,
        next_step="call pull_events(subscriber_id) to receive events since this cursor",
    ).model_dump()

register(name="subscribe", fn=_subscribe,
         description="Register as a named subscriber to the event bus. Call once per agent session, then poll with pull_events.",
         parameters={
             "subscriber_id": {"type": "string", "description": "Stable ID for this agent, e.g. 'cursor', 'claude', 'hermes'"},
             "topics": {"type": "array", "items": {"type": "string"}, "description": "Topic patterns to watch, e.g. ['process.*', 'run.*']"},
         })
```

### pull_events.py

```python
from navbe_notify import bus
from navbe_mcp.registry import register

def _pull_events(agent, user_id: str, subscriber_id: str, limit: int = 50) -> dict:
    events = bus.pull(subscriber_id, limit=limit)
    return {"events": events, "count": len(events),
            "next_step": "call pull_events again to poll for new events" if events else "no new events since last poll"}

register(name="pull_events", fn=_pull_events,
         description="Poll the event bus for events since this subscriber's last cursor. Returns up to limit events and advances the cursor.",
         parameters={
             "subscriber_id": {"type": "string"},
             "limit": {"type": "integer", "description": "Max events to return (default 50)"},
         })
```

### get_process_status.py

```python
from navbe_mcp.registry import register
from navbe_core.repository import WorkflowRepository
import json

def _get_process_status(agent, user_id: str, process_slug: str) -> dict:
    workflow = agent.repo.get_workflow_by_slug(process_slug)
    if workflow is None:
        return {"found": False, "process_slug": process_slug,
                "next_step": "call list_processes to see all known processes"}
    last_run = agent.repo.get_last_run(workflow.id)
    return {
        "found": True,
        "process_slug": process_slug,
        "workflow_id": workflow.id,
        "status": workflow.status,
        "next_run": workflow.scheduled_at.isoformat() if workflow.scheduled_at else None,
        "watermark": workflow.watermark_at.isoformat() if workflow.watermark_at else None,
        "last_run": {
            "run_id": last_run.id,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat(),
            "completed_at": last_run.completed_at.isoformat() if last_run.completed_at else None,
            "output": json.loads(last_run.output) if last_run.output else None,
        } if last_run else None,
    }

register(name="get_process_status", fn=_get_process_status,
         description="Get the live status of a named process (workflow). Any agent can call this — it reads shared hub state.",
         parameters={"process_slug": {"type": "string", "description": "Process name, e.g. 'langfuse_daily'"}})
```

### list_processes.py

```python
from navbe_mcp.registry import register

def _list_processes(agent, user_id: str) -> dict:
    workflows = agent.repo.list_workflows_with_slug(user_id)
    return {
        "processes": [
            {"process_slug": w.process_slug, "workflow_id": w.id,
             "status": w.status, "scheduled_at": w.scheduled_at.isoformat() if w.scheduled_at else None}
            for w in workflows
        ],
        "next_step": "call get_process_status(process_slug) for details on any process",
    }

register(name="list_processes", fn=_list_processes,
         description="List all named processes visible to all agents on this hub.")
```

### preview_workflow.py

```python
from navbe_mcp.registry import register

def _preview_workflow(agent, user_id: str, workflow_id: str) -> dict:
    """Run the workflow with LIMIT 5 extract into a temp DuckDB table. No watermark advance."""
    workflow = agent.repo.get_workflow(workflow_id, user_id)
    if workflow is None:
        return {"error": f"Workflow not found: {workflow_id}"}
    output = agent.run_now(workflow_id, user_id, mode="preview")
    return {**output, "preview": True,
            "note": "Watermark not advanced. Call run_workflow to execute for real."}

register(name="preview_workflow", fn=_preview_workflow,
         description="Dry-run a workflow: extracts sample rows, writes to a preview sandbox, does not advance watermarks.",
         parameters={"workflow_id": {"type": "string"}})
```

## Repository additions needed

Add to `navbe_core/repository.py`:

```python
def get_workflow_by_slug(self, process_slug: str) -> Optional[WorkflowModel]:
    return self.db.query(WorkflowModel).filter(
        WorkflowModel.process_slug == process_slug
    ).first()

def list_workflows_with_slug(self, user_id: str) -> list[WorkflowModel]:
    return self.db.query(WorkflowModel).filter(
        WorkflowModel.user_id == user_id,
        WorkflowModel.process_slug.isnot(None),
    ).order_by(WorkflowModel.created_at.desc()).all()
```

## SSE endpoint (navbe_api/sse.py)

Wire `bus.subscribe_queue()` / `bus.unsubscribe_queue()` into the existing SSE streaming endpoint. The SSE response JSON-encodes each event dict from the queue.

## Done when

- `bus.publish(...)` persists to SQLite and fans out to live queues
- `subscribe` + `pull_events` from two different MCP client sessions both see the same events
- `get_process_status("langfuse_daily")` returns the live status from either client
- SSE still works for the UI (same fan-out path)
