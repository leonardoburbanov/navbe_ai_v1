---
name: navbe-langfuse-sync
description: Implements Sprint 2 of Navbe — Langfuse incremental extraction (watermark, cost/token/tag fields), DuckDB schema v1 (raw traces + observations + retailer mart), the refresh_retailer_mart step, and the list_analysis_templates MCP tool. Use when extending the Langfuse connector, DuckDB destination DDL, navbe_transforms/tags.py, or the retailer aggregation mart.
---

# Navbe Langfuse Sync — Sprint 2

Full spec: [.cursor/plans/sprint2-mvp-a.md](.cursor/plans/sprint2-mvp-a.md)

## Key rules

- **Never drop rows on schema change** — if a new Langfuse field appears, add it to `extras` JSON. If a field disappears, use `None` / NULL.
- **Watermark advances only on success** — write `watermark_at` in `complete_run` callback, not during the run.
- **Dedup by natural key** — `ON CONFLICT (id) DO UPDATE SET ...` — already in the existing `write_traces_duckdb`; extend for new columns.
- **Mart refresh is idempotent** — `INSERT OR REPLACE` so re-running never creates duplicate retailer+date rows.

## Field extraction contract

`_extract_trace(t: dict) -> dict` must produce these columns:

| Column | Source | Type |
| --- | --- | --- |
| `id` | `t["id"]` | VARCHAR PK |
| `name` | `t["name"]` | VARCHAR |
| `timestamp` | `t["timestamp"]` | TIMESTAMPTZ |
| `user_id` | `t["userId"]` | VARCHAR |
| `tags` | `json.dumps(t.get("tags") or [])` | JSON |
| `prompt_tokens` | `t["usage"]["input"]` | INTEGER |
| `completion_tokens` | `t["usage"]["output"]` | INTEGER |
| `total_tokens` | `t["usage"]["total"]` | INTEGER |
| `total_cost` | `t["totalCost"]` | DOUBLE |
| `extras` | all unknown keys as JSON | JSON |

If any field is missing from the API response, use `None` — never abort the row.

## DuckDB DDL order

Apply in `open_destination()` before first write:
1. `CREATE TABLE IF NOT EXISTS traces (...)` — full schema above
2. `CREATE TABLE IF NOT EXISTS observations (...)` — adds `prompt_tokens`, `completion_tokens`, `total_tokens`, `total_cost`, `extras`
3. `CREATE TABLE IF NOT EXISTS mart_retailer_token_cost_daily (...)` — retailer + date grain

## Retailer tag extraction regex

```python
import re
_RETAILER_RE = re.compile(r"retailer:(\w+)")
```

Apply to each element of the `tags` JSON array. Return the first match, or `None`.

## Mart refresh SQL (DuckDB dialect)

The mart uses DuckDB's `json_extract` + `unnest` to parse the JSON tags array inline. The SQL lives in `navbe_transforms/tags.py` as a module-level constant `MART_REFRESH_SQL`. The `refresh_retailer_mart` step executes it against the destination DuckDB file.

## Watermark flow

```
run starts
  → _fetch_traces(since=workflow.watermark_at)   # None on first run
  → rows written to DuckDB
  → max(timestamp) from written rows stored in state["last_timestamp"]
run succeeds
  → repo.update_workflow_watermark(workflow_id, datetime.fromisoformat(last_timestamp))
```

## process_slug

`create_langfuse_export_workflow` sets `process_slug="langfuse_daily"` by default. Exposed as an optional parameter so future workflows can use different slugs.

## list_analysis_templates

Returns the retailer template only when the destination type is `duckdb`. The template object includes:
- `query_example`: a ready-to-run SELECT against `mart_retailer_token_cost_daily`
- `min_schema_version`: 1
- `next_step`: "use query_destination with the query_example to run the template"

## Done signal

1. `run_workflow("langfuse_daily")` writes rows to `traces` table with non-null `total_cost` and `tags`.
2. `mart_retailer_token_cost_daily` has rows grouped by `retailer_id + date`.
3. Second run: `new=0, changed=0` for previously synced rows; `watermark_at` on the workflow is updated.
4. `list_analysis_templates(destination_id=...)` returns the retailer template.
