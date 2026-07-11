# Sprint 2 — MVP A: Langfuse→DuckDB Incremental Sync

Targeted additions only. The dedup/upsert logic already works. This sprint adds watermark, missing Langfuse fields (cost/tokens/tags), the retailer mart, and the `list_analysis_templates` tool.

## Goal

`navbe daemon` + Cursor MCP → daily incremental Langfuse sync → DuckDB mart with tokens/cost per retailer. Second run is a no-op on already-synced rows; watermark advances only on success.

---

## 1. WorkflowModel schema additions

Add to `navbe_core/models.py` (additive only):

```python
class WorkflowModel(Base):
    # ... existing columns ...
    process_slug = Column(String, nullable=True, index=True)   # e.g. "langfuse_daily"
    watermark_at = Column(DateTime, nullable=True)             # high-water mark for next extract
```

Run `Base.metadata.create_all()` — SQLAlchemy adds columns if missing (safe for SQLite).

---

## 2. Langfuse field extraction (navbe_connectors/langfuse.py)

Extend `_fetch_traces` to pull cost/token/tag fields. Langfuse trace API returns:

```json
{
  "id": "...",
  "name": "...",
  "timestamp": "...",
  "userId": "...",
  "tags": ["retailer:123", "env:prod"],
  "usage": {
    "input": 450,
    "output": 120,
    "total": 570,
    "unit": "TOKENS"
  },
  "totalCost": 0.00342,
  "metadata": {}
}
```

Updated extraction:

```python
TRACE_CORE_FIELDS = ["id", "name", "timestamp", "userId"]
TRACE_COST_FIELDS = ["totalCost"]

def _extract_trace(t: dict) -> dict:
    usage = t.get("usage") or {}
    known = {
        "id": t.get("id"),
        "name": t.get("name"),
        "timestamp": t.get("timestamp"),
        "userId": t.get("userId"),
        "tags": json.dumps(t.get("tags") or []),
        "prompt_tokens": usage.get("input"),
        "completion_tokens": usage.get("output"),
        "total_tokens": usage.get("total"),
        "total_cost": t.get("totalCost"),
    }
    # extras: everything else that arrived, for resilience
    known_keys = {"id","name","timestamp","userId","tags","usage","totalCost","metadata"}
    extras = {k: v for k, v in t.items() if k not in known_keys}
    known["extras"] = json.dumps(extras) if extras else None
    return known
```

---

## 3. DuckDB DDL v1 (navbe_destinations/duckdb.py)

Replace the minimal DDL with a versioned schema. Applied once on `open_destination()`:

```sql
-- Raw landing table
CREATE TABLE IF NOT EXISTS traces (
    id               VARCHAR PRIMARY KEY,
    name             VARCHAR,
    timestamp        TIMESTAMPTZ,
    user_id          VARCHAR,
    tags             JSON,
    prompt_tokens    INTEGER,
    completion_tokens INTEGER,
    total_tokens     INTEGER,
    total_cost       DOUBLE,
    extras           JSON
);

CREATE TABLE IF NOT EXISTS observations (
    id                VARCHAR PRIMARY KEY,
    trace_id          VARCHAR,
    type              VARCHAR,
    name              VARCHAR,
    start_time        TIMESTAMPTZ,
    end_time          TIMESTAMPTZ,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    total_cost        DOUBLE,
    extras            JSON
);

-- Curated mart: tokens + cost per retailer per day
CREATE TABLE IF NOT EXISTS mart_retailer_token_cost_daily (
    retailer_id       VARCHAR NOT NULL,
    date              DATE NOT NULL,
    trace_count       INTEGER,
    prompt_tokens     BIGINT,
    completion_tokens BIGINT,
    total_tokens      BIGINT,
    total_cost        DOUBLE,
    PRIMARY KEY (retailer_id, date)
);
```

---

## 4. Retailer tag parse + mart refresh (navbe_transforms/tags.py)

```python
import json
import re

_RETAILER_RE = re.compile(r"retailer:(\w+)")


def extract_retailer_id(tags_json: str | None) -> str | None:
    """Return retailer_id from a JSON-encoded tags list, or None."""
    if not tags_json:
        return None
    tags = json.loads(tags_json)
    for tag in tags:
        m = _RETAILER_RE.search(str(tag))
        if m:
            return m.group(1)
    return None


MART_REFRESH_SQL = """
INSERT OR REPLACE INTO mart_retailer_token_cost_daily
    (retailer_id, date, trace_count, prompt_tokens, completion_tokens, total_tokens, total_cost)
SELECT
    regexp_extract(unnest(json_extract(tags, '$[*]')), 'retailer:(\\w+)', 1) AS retailer_id,
    CAST(timestamp AS DATE)                                                   AS date,
    COUNT(*)                                                                  AS trace_count,
    SUM(prompt_tokens)                                                        AS prompt_tokens,
    SUM(completion_tokens)                                                    AS completion_tokens,
    SUM(total_tokens)                                                         AS total_tokens,
    SUM(total_cost)                                                           AS total_cost
FROM traces
WHERE tags IS NOT NULL
  AND regexp_extract(unnest(json_extract(tags, '$[*]')), 'retailer:(\\w+)', 1) IS NOT NULL
GROUP BY retailer_id, date
ON CONFLICT (retailer_id, date) DO UPDATE SET
    trace_count       = excluded.trace_count,
    prompt_tokens     = excluded.prompt_tokens,
    completion_tokens = excluded.completion_tokens,
    total_tokens      = excluded.total_tokens,
    total_cost        = excluded.total_cost;
"""
```

Add a `refresh_retailer_mart` LangGraph step in `navbe_core/steps.py`:

```python
@step("refresh_retailer_mart")
def refresh_retailer_mart(state: dict) -> dict:
    db_path = state["dest_config"]["db_path"]
    con = duckdb.connect(db_path)
    con.execute(MART_REFRESH_SQL)
    con.close()
    return {"mart_refreshed": True}
```

Wire into the langfuse export graph after `write_traces`:
```python
# graph definition for langfuse_daily
{
    "entry": "fetch_traces",
    "nodes": ["fetch_traces", "write_traces", "refresh_retailer_mart"],
    "edges": [["fetch_traces","write_traces"], ["write_traces","refresh_retailer_mart"]]
}
```

---

## 5. Watermark

In `agent._on_fire` (and `run_now`), after successful run:

```python
from datetime import datetime, UTC

# extract max timestamp from output (write_traces returns last_ts in state)
last_ts_str = output.get("last_timestamp")
if last_ts_str:
    last_ts = datetime.fromisoformat(last_ts_str)
    repo.update_workflow_watermark(workflow_id, last_ts)
```

`write_traces_duckdb` should return `last_timestamp` = max timestamp of rows written.

`_fetch_traces` uses the stored watermark:
```python
watermark = repo.get_workflow(workflow_id, None).watermark_at
traces = _fetch_traces(host, public_key, secret_key, limit=50, since=watermark)
```

Add to repository:
```python
def update_workflow_watermark(self, workflow_id: str, watermark: datetime) -> None:
    self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).update(
        {"watermark_at": watermark}
    )
    self.db.commit()
```

---

## 6. create_langfuse_export_workflow — add process_slug

```python
def create_langfuse_export_workflow(self, ...) -> WorkflowModel:
    # ... existing code ...
    workflow = self.schedule(
        ...,
        process_slug="langfuse_daily",   # default; allow override
    )
    return workflow
```

---

## 7. list_analysis_templates MCP tool

```python
def _list_analysis_templates(agent, user_id: str, destination_id: str) -> dict:
    dest = agent.repo.get_destination(destination_id, user_id)
    if dest is None:
        return {"error": "Destination not found"}
    templates = []
    if dest.type == "duckdb":
        templates.append({
            "id": "retailer_token_cost_daily",
            "name": "Tokens & cost per retailer per day",
            "description": "Aggregates prompt/completion tokens and cost from Langfuse traces tagged retailer:[id]",
            "min_schema_version": 1,
            "query_example": "SELECT * FROM mart_retailer_token_cost_daily ORDER BY date DESC, total_cost DESC LIMIT 20",
        })
    return {"templates": templates,
            "next_step": "Use query_destination with the query_example to run the template"}
```

---

## Done when

1. `create_connection` → `create_destination` → `schedule_workflow(cron="0 2 * * *")` creates `langfuse_daily`.
2. First run: traces land in `traces` table with tokens/cost/tags; mart has rows grouped by retailer + date.
3. Second run: `new=0, changed=0` for already-synced rows; watermark advanced to last seen timestamp.
4. `list_analysis_templates` returns the retailer template.
5. `query_destination(sql="SELECT * FROM mart_retailer_token_cost_daily LIMIT 5")` returns data.
