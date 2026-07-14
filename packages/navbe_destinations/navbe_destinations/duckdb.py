"""DuckDB destination: schema v1, upsert writes, observation flatten."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import duckdb

# ponytail: avoid importing navbe_core here (keeps destinations → core one-way)


def _default_data_dir() -> str:
    """Return the Navbe data directory under the profile home."""
    home = Path(os.environ.get("NAVBE_HOME", Path.home() / ".navbe"))
    data = home / "data"
    data.mkdir(parents=True, exist_ok=True)
    return str(data)


TRACE_FIELDS = [
    "id",
    "name",
    "timestamp",
    "user_id",
    "tags",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "total_cost",
    "extras",
]
OBSERVATION_FIELDS = [
    "id",
    "trace_id",
    "type",
    "name",
    "start_time",
    "end_time",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "total_cost",
    "extras",
]
DESTINATION_TYPES = {"csv_file", "duckdb", "sqlite", "email"}

SCHEMA_VERSION = 1

# ponytail: timestamps as VARCHAR — avoids pytz for TIMESTAMPTZ Python round-trips;
# mart SQL uses try_cast. Upgrade to TIMESTAMPTZ + tzdata if analytics needs native types.
_TRACES_DDL = """
CREATE TABLE IF NOT EXISTS traces (
    id                VARCHAR PRIMARY KEY,
    name              VARCHAR,
    timestamp         VARCHAR,
    user_id           VARCHAR,
    tags              JSON,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    total_cost        DOUBLE,
    extras            JSON
)
"""

_OBSERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS observations (
    id                VARCHAR PRIMARY KEY,
    trace_id          VARCHAR,
    type              VARCHAR,
    name              VARCHAR,
    start_time        VARCHAR,
    end_time          VARCHAR,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    total_cost        DOUBLE,
    extras            JSON
)
"""

_MART_DDL = """
CREATE TABLE IF NOT EXISTS mart_retailer_token_cost_daily (
    retailer_id       VARCHAR NOT NULL,
    date              DATE NOT NULL,
    trace_count       INTEGER,
    prompt_tokens     BIGINT,
    completion_tokens BIGINT,
    total_tokens      BIGINT,
    total_cost        DOUBLE,
    PRIMARY KEY (retailer_id, date)
)
"""

_REPLAY_RESULTS_DDL = """
CREATE TABLE IF NOT EXISTS replay_results (
    id VARCHAR PRIMARY KEY,
    trace_id VARCHAR NOT NULL,
    api_url VARCHAR NOT NULL,
    request_body JSON,
    response_body JSON,
    status_code INTEGER,
    latency_ms DOUBLE,
    original_output JSON,
    diff_summary JSON,
    ts VARCHAR NOT NULL,
    extras JSON
)
"""

# Additive columns for DBs created before schema v1.
_TRACE_ADD_COLUMNS = [
    ("user_id", "VARCHAR"),
    ("tags", "JSON"),
    ("prompt_tokens", "INTEGER"),
    ("completion_tokens", "INTEGER"),
    ("total_tokens", "INTEGER"),
    ("total_cost", "DOUBLE"),
    ("extras", "JSON"),
]
_OBS_ADD_COLUMNS = [
    ("trace_id", "VARCHAR"),
    ("prompt_tokens", "INTEGER"),
    ("completion_tokens", "INTEGER"),
    ("total_tokens", "INTEGER"),
    ("total_cost", "DOUBLE"),
    ("extras", "JSON"),
]


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Apply schema v1 DDL and additive column migrations."""
    con.execute(_TRACES_DDL)
    con.execute(_OBSERVATIONS_DDL)
    con.execute(_MART_DDL)
    con.execute(_REPLAY_RESULTS_DDL)
    for col, typ in _TRACE_ADD_COLUMNS:
        con.execute(f"ALTER TABLE traces ADD COLUMN IF NOT EXISTS {col} {typ}")
    for col, typ in _OBS_ADD_COLUMNS:
        con.execute(f"ALTER TABLE observations ADD COLUMN IF NOT EXISTS {col} {typ}")


def list_replay_results(db_path: str, limit: int = 50) -> list[dict]:
    """Return recent replay_results rows from a DuckDB file."""
    import json as _json

    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "replay_results" not in tables:
            return []
        rows = con.execute(
            """
            SELECT id, trace_id, api_url, request_body, response_body, status_code,
                   latency_ms, original_output, diff_summary, ts
            FROM replay_results
            ORDER BY ts DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
    finally:
        con.close()

    def _parse(v: object) -> object:
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except _json.JSONDecodeError:
                return v
        return v

    return [
        {
            "id": r[0],
            "trace_id": r[1],
            "api_url": r[2],
            "request_body": _parse(r[3]),
            "response_body": _parse(r[4]),
            "status_code": r[5],
            "latency_ms": r[6],
            "original_output": _parse(r[7]),
            "compare": _parse(r[8]),
            "ts": r[9],
        }
        for r in rows
    ]


def flatten_observations(traces: list[dict]) -> list[dict]:
    """Turn per-trace observation lists into flat rows keyed by trace_id."""
    rows = []
    for trace in traces:
        for obs in trace.get("observations") or []:
            if "trace_id" in obs and "start_time" in obs:
                rows.append({k: obs.get(k) for k in OBSERVATION_FIELDS})
            else:
                rows.append(
                    {
                        "id": obs.get("id"),
                        "trace_id": obs.get("trace_id") or obs.get("traceId") or trace.get("id"),
                        "type": obs.get("type"),
                        "name": obs.get("name"),
                        "start_time": obs.get("start_time") or obs.get("startTime"),
                        "end_time": obs.get("end_time") or obs.get("endTime"),
                        "prompt_tokens": obs.get("prompt_tokens"),
                        "completion_tokens": obs.get("completion_tokens"),
                        "total_tokens": obs.get("total_tokens"),
                        "total_cost": obs.get("total_cost"),
                        "extras": obs.get("extras"),
                    }
                )
    return rows


def write_traces_csv(traces: list[dict], folder: str, filename: str) -> str:
    """Write traces to a CSV file (core fields only)."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    csv_fields = ["id", "name", "timestamp", "user_id", "tags", "total_tokens", "total_cost"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: trace.get(field) for field in csv_fields} for trace in traces)

    return path


def _row_tuple(row: dict, fields: list[str]) -> tuple:
    return tuple(row.get(f) for f in fields)


def write_traces_duckdb(
    traces: list[dict], db_path: str, table: str = "traces", mode: str = "append"
) -> tuple[str, dict]:
    """Write `traces` into DuckDB, keyed by `id`, incrementally by default.

    Returns (db_path, stats) where stats includes new/changed/deleted and
    last_timestamp (max timestamp among rows in this batch, or None).
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    other_fields = [f for f in TRACE_FIELDS if f != "id"]

    con = duckdb.connect(db_path)
    try:
        ensure_schema(con)
        # Custom table name: create with same shape if not the default.
        if table != "traces":
            cols = ", ".join(f"{f} VARCHAR" for f in TRACE_FIELDS)
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols}, PRIMARY KEY (id))')

        existing = {
            row[0]: tuple(row[1:])
            for row in con.execute(f'SELECT {", ".join(TRACE_FIELDS)} FROM "{table}"').fetchall()
        }
        incoming_ids = {t.get("id") for t in traces}
        stats: dict = {
            "new": sum(1 for t in traces if t.get("id") not in existing),
            "changed": sum(
                1
                for t in traces
                if t.get("id") in existing and existing[t["id"]] != _row_tuple(t, other_fields)
            ),
            "deleted": sum(1 for i in existing if i not in incoming_ids)
            if mode == "overwrite"
            else 0,
        }

        if mode == "overwrite":
            con.execute(f'DELETE FROM "{table}"')

        rows = [[trace.get(field) for field in TRACE_FIELDS] for trace in traces]
        if rows:
            placeholders = ", ".join("?" for _ in TRACE_FIELDS)
            update_clause = ", ".join(f"{f} = excluded.{f}" for f in other_fields)
            con.executemany(
                f'INSERT INTO "{table}" ({", ".join(TRACE_FIELDS)}) VALUES ({placeholders}) '
                f"ON CONFLICT (id) DO UPDATE SET {update_clause}",
                rows,
            )

        timestamps = [t.get("timestamp") for t in traces if t.get("timestamp")]
        stats["last_timestamp"] = max(timestamps) if timestamps else None
    finally:
        con.close()

    return db_path, stats


def write_observations_duckdb(
    observations: list[dict], db_path: str, table: str = "observations", mode: str = "append"
) -> tuple[str, dict]:
    """Write observation rows into DuckDB, keyed by observation `id`."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    other_fields = [f for f in OBSERVATION_FIELDS if f != "id"]

    con = duckdb.connect(db_path)
    try:
        ensure_schema(con)
        if table != "observations":
            cols = ", ".join(f"{f} VARCHAR" for f in OBSERVATION_FIELDS)
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols}, PRIMARY KEY (id))')

        existing = {
            row[0]: tuple(row[1:])
            for row in con.execute(
                f'SELECT {", ".join(OBSERVATION_FIELDS)} FROM "{table}"'
            ).fetchall()
        }
        incoming_ids = {o.get("id") for o in observations}
        stats = {
            "new": sum(1 for o in observations if o.get("id") not in existing),
            "changed": sum(
                1
                for o in observations
                if o.get("id") in existing and existing[o["id"]] != _row_tuple(o, other_fields)
            ),
            "deleted": sum(1 for i in existing if i not in incoming_ids)
            if mode == "overwrite"
            else 0,
        }

        if mode == "overwrite":
            con.execute(f'DELETE FROM "{table}"')

        rows = [[obs.get(field) for field in OBSERVATION_FIELDS] for obs in observations]
        if rows:
            placeholders = ", ".join("?" for _ in OBSERVATION_FIELDS)
            update_clause = ", ".join(f"{f} = excluded.{f}" for f in other_fields)
            con.executemany(
                f'INSERT INTO "{table}" ({", ".join(OBSERVATION_FIELDS)}) VALUES ({placeholders}) '
                f"ON CONFLICT (id) DO UPDATE SET {update_clause}",
                rows,
            )
    finally:
        con.close()

    return db_path, stats


def write_observations(
    traces: list[dict], destination_type: str, config: dict, mode: str = "append"
) -> dict:
    """Write flattened observations from `traces` to the destination."""
    observations = flatten_observations(traces)
    if destination_type != "duckdb":
        return {
            "observation_table": None,
            "observation_count": len(observations),
            "new": 0,
            "changed": 0,
            "deleted": 0,
        }

    db_path = config.get("db_path") or os.path.join(_default_data_dir(), "langfuse.duckdb")
    table = config.get("observations_table") or "observations"
    _, stats = write_observations_duckdb(observations, db_path, table=table, mode=mode)
    return {"observation_table": table, "observation_count": len(observations), **stats}


def write_traces(
    traces: list[dict], destination_type: str, config: dict, workflow_id: str, mode: str = "append"
) -> dict:
    """Write `traces` to the given destination, returning output fields for the run."""
    if destination_type == "csv_file":
        folder = config.get("folder") or _default_data_dir()
        path = write_traces_csv(traces, folder, f"{workflow_id}.csv")
        timestamps = [t.get("timestamp") for t in traces if t.get("timestamp")]
        return {
            "output_path": path,
            "new": len(traces),
            "changed": 0,
            "deleted": 0,
            "last_timestamp": max(timestamps) if timestamps else None,
        }

    if destination_type == "duckdb":
        db_path = config.get("db_path") or os.path.join(_default_data_dir(), "langfuse.duckdb")
        table = config.get("table") or "traces"
        path, stats = write_traces_duckdb(traces, db_path, table, mode=mode)
        return {"output_path": path, "table": table, **stats}

    raise ValueError(f"Unsupported destination type: {destination_type}")
