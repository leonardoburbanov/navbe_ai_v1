import os

import duckdb

from navbe_core.config import DATA_DIR

DEFAULT_PAGE_SIZE = 10  # small enough to render as a table in a chat reply
MAX_PAGE_SIZE = 200


def _open_destination(destination_type: str, config: dict) -> duckdb.DuckDBPyConnection:
    """Open a connection exposing this destination's data as a view named
    `traces`, regardless of the underlying storage — callers always query
    `traces`, never the destination's internal table name or file layout.
    """
    if destination_type == "duckdb":
        db_path = config.get("db_path") or os.path.join(str(DATA_DIR), "langfuse.duckdb")
        table = config.get("table") or "traces"
        con = duckdb.connect(db_path, read_only=True)
        if table != "traces":
            con.execute(f'CREATE VIEW traces AS SELECT * FROM "{table}"')
        return con

    if destination_type == "csv_file":
        folder = config.get("folder") or str(DATA_DIR)
        pattern = os.path.join(folder, "*.csv")
        con = duckdb.connect(":memory:")
        con.execute(
            f"CREATE VIEW traces AS SELECT * FROM read_csv('{pattern}', union_by_name=true)"
        )
        return con

    raise ValueError(f"Unsupported destination type: {destination_type}")


def describe_destination(destination_type: str, config: dict) -> dict:
    con = _open_destination(destination_type, config)
    try:
        columns = con.execute("DESCRIBE traces").fetchall()
        return {"columns": [{"name": c[0], "type": c[1]} for c in columns]}
    finally:
        con.close()


def query_destination(
    destination_type: str, config: dict, sql: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
) -> dict:
    """Run a read-only SQL query against a destination's `traces` view,
    paginated. Defaults to 10 rows per page — small enough to read as a
    table in a chat reply; raise page_size for programmatic use, up to
    MAX_PAGE_SIZE.

    ponytail: a single startswith('select') check, not a real SQL sandbox —
    upgrade to a proper read-only role/grant if this is ever exposed beyond
    trusted MCP clients.
    """
    inner_sql = sql.strip().rstrip(";")
    if not inner_sql.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed")

    page = max(page, 1)
    page_size = max(min(page_size, MAX_PAGE_SIZE), 1)

    con = _open_destination(destination_type, config)
    try:
        count_row = con.execute(f"SELECT count(*) FROM ({inner_sql}) AS _query").fetchone()
        total = count_row[0] if count_row is not None else 0
        result = con.execute(
            f"SELECT * FROM ({inner_sql}) AS _query LIMIT ? OFFSET ?",
            [page_size, (page - 1) * page_size],
        )
        columns = [d[0] for d in result.description]
        rows = result.fetchall()
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    finally:
        con.close()
