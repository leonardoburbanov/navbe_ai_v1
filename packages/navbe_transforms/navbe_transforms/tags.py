"""Tag parsing and retailer mart refresh SQL."""

from __future__ import annotations

import json
import re

_RETAILER_RE = re.compile(r"retailer:(\w+)")

# ponytail: full rebuild of the small mart each run — swap for incremental
# merge when mart row counts get large.
# Token columns are VARCHAR in DuckDB; try_cast before SUM.
# Langfuse often leaves traces.prompt_tokens NULL — fall back to SUM(observations).
MART_REFRESH_SQL = """
DELETE FROM mart_retailer_token_cost_daily;
INSERT INTO mart_retailer_token_cost_daily
    (retailer_id, date, trace_count, prompt_tokens, completion_tokens, total_tokens, total_cost)
WITH obs_by_trace AS (
    SELECT
        CAST(trace_id AS VARCHAR) AS trace_id,
        COALESCE(SUM(try_cast(prompt_tokens AS BIGINT)), 0) AS prompt_tokens,
        COALESCE(SUM(try_cast(completion_tokens AS BIGINT)), 0) AS completion_tokens,
        COALESCE(SUM(try_cast(total_tokens AS BIGINT)), 0) AS total_tokens
    FROM observations
    GROUP BY 1
),
enriched AS (
    SELECT
        t.id,
        t.tags,
        t.timestamp,
        COALESCE(try_cast(t.prompt_tokens AS BIGINT), o.prompt_tokens, 0) AS prompt_tokens,
        COALESCE(
            try_cast(t.completion_tokens AS BIGINT), o.completion_tokens, 0
        ) AS completion_tokens,
        COALESCE(try_cast(t.total_tokens AS BIGINT), o.total_tokens, 0) AS total_tokens,
        COALESCE(try_cast(t.total_cost AS DOUBLE), 0) AS total_cost
    FROM traces t
    LEFT JOIN obs_by_trace o ON o.trace_id = CAST(t.id AS VARCHAR)
),
exploded AS (
    SELECT
        regexp_extract(tag, 'retailer:(\\w+)', 1) AS retailer_id,
        CAST(try_cast(timestamp AS TIMESTAMPTZ) AS DATE) AS date,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        total_cost
    FROM enriched,
         UNNEST(from_json(CAST(tags AS VARCHAR), '["VARCHAR"]')) AS _(tag)
    WHERE tags IS NOT NULL
)
SELECT
    retailer_id,
    date,
    COUNT(*)::INTEGER,
    COALESCE(SUM(prompt_tokens), 0)::BIGINT,
    COALESCE(SUM(completion_tokens), 0)::BIGINT,
    COALESCE(SUM(total_tokens), 0)::BIGINT,
    COALESCE(SUM(total_cost), 0)::DOUBLE
FROM exploded
WHERE retailer_id IS NOT NULL AND retailer_id <> ''
GROUP BY retailer_id, date
"""


def extract_retailer_id(tags_json: str | None) -> str | None:
    """Return retailer_id from a JSON-encoded tags list, or None."""
    if not tags_json:
        return None
    tags = json.loads(tags_json)
    for tag in tags:
        match = _RETAILER_RE.search(str(tag))
        if match:
            return match.group(1)
    return None
