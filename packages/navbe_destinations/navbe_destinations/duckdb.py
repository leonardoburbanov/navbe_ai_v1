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


TRACE_FIELDS = ["id", "name", "timestamp", "userId"]
OBSERVATION_FIELDS = ["id", "traceId", "type", "name", "startTime", "endTime"]
DESTINATION_TYPES = {"csv_file", "duckdb"}


def flatten_observations(traces: list[dict]) -> list[dict]:
    """Turn per-trace observation lists into flat rows keyed by traceId."""
    rows = []
    for trace in traces:
        for obs in trace.get("observations") or []:
            rows.append(
                {
                    "id": obs.get("id"),
                    "traceId": trace.get("id"),
                    "type": obs.get("type"),
                    "name": obs.get("name"),
                    "startTime": obs.get("startTime"),
                    "endTime": obs.get("endTime"),
                }
            )
    return rows


def write_traces_csv(traces: list[dict], folder: str, filename: str) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACE_FIELDS)
        writer.writeheader()
        writer.writerows({field: trace.get(field) for field in TRACE_FIELDS} for trace in traces)

    return path


def write_traces_duckdb(
    traces: list[dict], db_path: str, table: str, mode: str = "append"
) -> tuple[str, dict]:
    """Write `traces` into `table`, keyed by trace `id`, incrementally by default.

    mode="append" (default) inserts ids not yet present and updates ids whose
    other fields changed, so re-running a workflow never duplicates rows.
    mode="overwrite" clears the table first, so it only ever holds this run's
    traces.

    Returns (db_path, stats) where stats = {"new", "changed", "deleted"} counts
    how this write changed the destination.

    ponytail: "deleted" is only meaningful in overwrite mode, since that's the
    only case where `traces` is the full current source state. In append mode
    we only ever see the latest page of traces, so anything missing from it
    could simply be outside that page, not actually deleted — counted as 0.
    Also, dedup relies on the PRIMARY KEY set at table creation; a table
    created before this constraint existed won't have one — drop and let it
    recreate if ON CONFLICT errors on an old table.
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    other_fields = [f for f in TRACE_FIELDS if f != "id"]

    con = duckdb.connect(db_path)
    try:
        columns = ", ".join(f'"{field}" VARCHAR' for field in TRACE_FIELDS)
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({columns}, PRIMARY KEY ("id"))')

        existing = {
            row[0]: tuple(row[1:]) for row in con.execute(f'SELECT * FROM "{table}"').fetchall()
        }
        incoming_ids = {t.get("id") for t in traces}
        stats = {
            "new": sum(1 for t in traces if t.get("id") not in existing),
            "changed": sum(
                1
                for t in traces
                if t.get("id") in existing
                and existing[t["id"]] != tuple(t.get(f) for f in other_fields)
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
            update_clause = ", ".join(f'"{f}" = excluded."{f}"' for f in other_fields)
            con.executemany(
                f'INSERT INTO "{table}" VALUES ({placeholders}) '
                f'ON CONFLICT ("id") DO UPDATE SET {update_clause}',
                rows,
            )
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
        columns = ", ".join(f'"{field}" VARCHAR' for field in OBSERVATION_FIELDS)
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({columns}, PRIMARY KEY ("id"))')

        existing = {
            row[0]: tuple(row[1:]) for row in con.execute(f'SELECT * FROM "{table}"').fetchall()
        }
        incoming_ids = {o.get("id") for o in observations}
        stats = {
            "new": sum(1 for o in observations if o.get("id") not in existing),
            "changed": sum(
                1
                for o in observations
                if o.get("id") in existing
                and existing[o["id"]] != tuple(o.get(f) for f in other_fields)
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
            update_clause = ", ".join(f'"{f}" = excluded."{f}"' for f in other_fields)
            con.executemany(
                f'INSERT INTO "{table}" VALUES ({placeholders}) '
                f'ON CONFLICT ("id") DO UPDATE SET {update_clause}',
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
    """Write `traces` to the given destination, returning fields to merge
    into the workflow run's output: always `output_path`, plus `new`/`changed`/
    `deleted` row counts for this write.

    `mode` only affects the duckdb destination — each csv_file run already
    writes its own fresh `{workflow_id}.csv`, so append/overwrite don't apply
    there; every row in it counts as "new".
    """
    if destination_type == "csv_file":
        folder = config.get("folder") or _default_data_dir()
        path = write_traces_csv(traces, folder, f"{workflow_id}.csv")
        return {"output_path": path, "new": len(traces), "changed": 0, "deleted": 0}

    if destination_type == "duckdb":
        db_path = config.get("db_path") or os.path.join(_default_data_dir(), "langfuse.duckdb")
        table = config.get("table") or "traces"
        path, stats = write_traces_duckdb(traces, db_path, table, mode=mode)
        return {"output_path": path, "table": table, **stats}

    raise ValueError(f"Unsupported destination type: {destination_type}")
