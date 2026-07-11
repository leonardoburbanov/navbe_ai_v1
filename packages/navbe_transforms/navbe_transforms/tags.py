"""Tag parsing and retailer mart refresh SQL."""

from __future__ import annotations

import json
import re

_RETAILER_RE = re.compile(r"retailer:(\w+)")

# ponytail: full rebuild of the small mart each run — swap for incremental
# merge when mart row counts get large.
MART_REFRESH_SQL = """
DELETE FROM mart_retailer_token_cost_daily;
INSERT INTO mart_retailer_token_cost_daily
    (retailer_id, date, trace_count, prompt_tokens, completion_tokens, total_tokens, total_cost)
WITH exploded AS (
    SELECT
        regexp_extract(tag, 'retailer:(\\w+)', 1) AS retailer_id,
        CAST(try_cast(timestamp AS TIMESTAMPTZ) AS DATE) AS date,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        total_cost
    FROM traces,
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
