---
name: navbe-event-bus
description: Implements Sprint 1 of Navbe — the durable SQLite pub/sub event bus and the five multi-agent MCP tools (subscribe, pull_events, get_process_status, list_processes, preview_workflow). Use when adding the event bus, subscriber cursors, or any of these MCP tools to navbe_notify or navbe_mcp.
---

# Navbe Event Bus — Sprint 1

Full spec: [.cursor/plans/sprint1-event-bus.md](.cursor/plans/sprint1-event-bus.md)

## Core contract

`navbe_notify/bus.py` exposes four functions — the rest of the codebase only calls these:

| Function | What it does |
| --- | --- |
| `init(db_path)` | Create `events` + `subscriber_cursors` tables; call once at daemon startup |
| `publish(topic, type_, payload)` | INSERT into events table + fan-out to SSE queues |
| `register_subscriber(subscriber_id)` | Idempotent upsert into subscriber_cursors |
| `pull(subscriber_id, limit)` | SELECT events > cursor; advance cursor; return list |

## Key invariants

- **Durability**: `publish` always writes to SQLite before fan-out. A subscriber that connects after the event is published still sees it via `pull`.
- **Independent cursors**: each `subscriber_id` has its own `last_event_id`. Pulling for `cursor` does not affect `claude`'s position.
- **Thread safety**: `publish` is called from APScheduler worker threads. Use `_loop.call_soon_threadsafe` for SSE queue fan-out — same pattern as the original `events.py`.
- **Topics** follow the pattern `process.{slug}`, `run.{id}`, `system`. Subscribers filter in application code, not in SQL (keeps the schema simple).

## Publish call sites in agent.py

Replace all `events.publish({...})` with `bus.publish(topic, type_, payload)`:

```python
# run started
bus.publish(f"run.{run.id}", "run.started",
            {"workflow_id": workflow_id, "run_id": run.id,
             "process_slug": workflow.process_slug})

# step completed (inside _execute stream loop)
bus.publish(f"run.{run_id}", "run.step",
            {"step": step_name, "workflow_id": workflow_id, "status": "succeeded"})

# run succeeded
bus.publish(f"process.{workflow.process_slug}", "run.succeeded",
            {"workflow_id": workflow_id, "run_id": run.id})

# run failed
bus.publish(f"process.{workflow.process_slug}", "run.failed",
            {"workflow_id": workflow_id, "run_id": run.id, "error": str(e)})
```

## MCP tool file pattern

Each new tool lives in `navbe_mcp/tools/<name>.py` and calls `register(...)` at import time:

```python
from navbe_mcp.registry import register
from pydantic import BaseModel

class MyResult(BaseModel):
    ...
    next_step: str

def _my_tool(agent, user_id: str, ...) -> dict:
    ...
    return MyResult(...).model_dump()

register(name="my_tool", fn=_my_tool, description="...", parameters={...})
```

Import the module in `navbe_api/app.py` lifespan so registration fires at startup.

## Repository methods to add (navbe_core/repository.py)

```python
def get_workflow_by_slug(self, process_slug: str) -> Optional[WorkflowModel]: ...
def list_workflows_with_slug(self, user_id: str) -> list[WorkflowModel]: ...
```

## preview_workflow behaviour

- Mode `"preview"` in `agent.run_now`: pass `LIMIT 5` to connector extract and write to a temp DuckDB path (`{data_dir}/preview_{workflow_id}.duckdb`).
- Do **not** advance `watermark_at`. Do **not** publish `run.succeeded` on the process topic — publish `run.preview.completed` instead.
- Temp file is deleted at end of preview run.

## Done signal

Two separate MCP sessions calling `pull_events(subscriber_id="cursor")` and `pull_events(subscriber_id="claude")` independently see the same `run.succeeded` event published during a workflow run. `get_process_status("langfuse_daily")` returns identical data from both.
