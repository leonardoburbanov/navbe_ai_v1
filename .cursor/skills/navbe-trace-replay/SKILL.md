---
name: navbe-trace-replay
description: Implements Sprint 4 of Navbe — the replay_trace_to_api MCP tool, the four LangGraph steps (fetch_trace, call_api, compare_outputs, store_replay), the replay_results DuckDB table, and the UI Replays page. Use when building or modifying trace replay, API comparison, the _diff function, or the ReplayRequest/CompareResult Pydantic models.
---

# Navbe Trace Replay — Sprint 4

Full spec: [.cursor/plans/sprint4-mvp-b.md](.cursor/plans/sprint4-mvp-b.md)

## Data flow

```
replay_trace_to_api(MCP tool)
  → fetch_trace    (Langfuse API → trace input + output)
  → call_api       (target API with auth → response + latency)
  → compare_outputs(_diff(trace_output, api_response) → CompareResult)
  → store_replay   (upsert into DuckDB replay_results, if destination_id given)
  → return ReplayResult
```

## Pydantic models (navbe_core/models_replay.py)

`AuthConfig` and `ReplayRequest` are the MCP tool inputs. `CompareResult` and `ReplayResult` are the outputs. Every field that crosses a boundary (MCP response, REST response) must be typed.

`AuthConfig.token` and `AuthConfig.password` are stored encrypted (Fernet, same key as secrets). Never log them.

## _diff rules

`_diff(expected, actual, path)` is a pure recursive function. Rules:
- `dict`: recurse over union of keys
- `list`: recurse index-by-index; flag length mismatch separately
- scalar: emit a `DiffEntry` only when `expected != actual`
- Return `[]` when identical (no diff entries)

This function is directly testable with pytest — see sprint plan for 4 required test cases.

## call_api auth wiring

| `auth.type` | What to do |
| --- | --- |
| `none` | No auth header |
| `bearer` | `Authorization: Bearer {token}` |
| `api_key` | `{auth.header}: {token}` (default header is `Authorization`) |
| `basic` | `httpx` `auth=(username, password)` |

Never add auth logic outside this step. Do not pass raw credentials in the LangGraph state dict beyond what the step needs.

## store_replay DuckDB table

- Primary key: generated UUID (`replay_id`)
- `diff_summary` column: `CompareResult.model_dump()` serialized as JSON
- `extras` column: JSON, always `None` for now (reserved for unknown API response fields)
- Create table with `CREATE TABLE IF NOT EXISTS` — idempotent; safe to call every run

## save_as_workflow path

When `save_as_workflow=True`:
- Store the replay graph IR (same 4 nodes) in a new `WorkflowModel` via `agent.schedule`
- The `input` in the IR stores `connection_id` and `destination_id` (not raw credentials)
- `process_slug` = `f"replay_{trace_id[:8]}"`
- Return `workflow_id` in `ReplayResult`

The saved workflow can be re-run via `run_workflow(workflow_id)` or scheduled.

## Replays page (apps/web)

Calls `GET /api/replays?workflow_id=...` (or without param for all replays).

Diff badge logic:
```ts
function diffBadge(row: ReplayRow) {
  if (row.status_code >= 400) return { label: "error",     color: "red"   }
  if (row.compare.identical)  return { label: "identical", color: "green" }
  return { label: `${row.compare.diff_count} diffs`,       color: "amber" }
}
```

Row expand shows a two-column JSON view: `original_output` (left) vs `response_body` (right). Highlight paths listed in `compare.diffs[].path`.

## Done signal

1. `replay_trace_to_api(trace_id=..., connection_id=..., api_url=..., auth={type:"bearer",token:"..."})` returns `CompareResult`.
2. With `destination_id`, row appears in `replay_results` table.
3. Replays page shows the row with correct diff badge.
4. `pytest packages/navbe_core/tests/test_compare.py` passes (4 cases).
5. `save_as_workflow=True` creates a workflow visible via `list_processes`.
