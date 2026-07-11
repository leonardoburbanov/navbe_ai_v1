"""Tag parsing helpers (Sprint 2 fills in retailer:[id] extraction)."""

from __future__ import annotations

import json
import re

_RETAILER_RE = re.compile(r"retailer:(\w+)")


def extract_retailer_id(tags_json: str | None) -> str | None:
    """Return retailer_id from a JSON-encoded tags list, or None.

    Stub for Sprint 2 — used by the retailer token/cost mart.
    """
    if not tags_json:
        return None
    tags = json.loads(tags_json)
    for tag in tags:
        match = _RETAILER_RE.search(str(tag))
        if match:
            return match.group(1)
    return None
