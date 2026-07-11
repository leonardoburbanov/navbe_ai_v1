"""Durable SQLite pub/sub event bus with per-subscriber cursors.

publish() always persists before fan-out so late-joining agents can pull_events.
Live SSE clients still get in-process queue fan-out.

ponytail: single SQLite file for events → NATS/Redis if multi-process needed.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

# ponytail: single SQLite file for events; swap for NATS if multi-process needed
_DB: Path | None = None
_subscribers: set[asyncio.Queue] = set()
_loop: asyncio.AbstractEventLoop | None = None


def init(db_path: Path) -> None:
    """Create events + subscriber_cursors tables. Call once at daemon startup."""
    global _DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _DB = db_path
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            topic     TEXT NOT NULL,
            type      TEXT NOT NULL,
            payload   TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS subscriber_cursors (
            subscriber_id TEXT PRIMARY KEY,
            last_event_id INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT NOT NULL
        );
        """
    )
    con.close()


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Bind the running event loop so publish() can fan out from worker threads."""
    global _loop
    _loop = loop


def subscribe_queue() -> asyncio.Queue:
    """Register a live SSE client queue (fan-out only; no cursor)."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)
    return queue


def unsubscribe_queue(queue: asyncio.Queue) -> None:
    """Remove a live SSE client queue."""
    _subscribers.discard(queue)


# Aliases kept for SSE helpers that still call subscribe/unsubscribe
subscribe = subscribe_queue
unsubscribe = unsubscribe_queue


def publish(topic: str, type_: str, payload: dict | None = None) -> int:
    """Persist event then fan-out to live SSE queues. Returns event id."""
    assert _DB is not None, "bus.init() not called"
    body = payload or {}
    ts = datetime.now(UTC).isoformat()
    con = sqlite3.connect(_DB)
    cur = con.execute(
        "INSERT INTO events(ts, topic, type, payload) VALUES (?,?,?,?)",
        (ts, topic, type_, json.dumps(body)),
    )
    event_id = cur.lastrowid or 0
    con.commit()
    con.close()

    event = {"id": event_id, "ts": ts, "topic": topic, "type": type_, **body}
    if _loop is not None:
        for queue in list(_subscribers):
            _loop.call_soon_threadsafe(queue.put_nowait, event)
    return event_id


def register_subscriber(subscriber_id: str) -> None:
    """Idempotent upsert of a subscriber cursor (starts at event 0)."""
    assert _DB is not None, "bus.init() not called"
    con = sqlite3.connect(_DB)
    con.execute(
        """
        INSERT INTO subscriber_cursors(subscriber_id, last_event_id, updated_at)
        VALUES (?, 0, ?)
        ON CONFLICT(subscriber_id) DO NOTHING
        """,
        (subscriber_id, datetime.now(UTC).isoformat()),
    )
    con.commit()
    con.close()


def pull(subscriber_id: str, limit: int = 50) -> list[dict]:
    """Return up to `limit` events after this subscriber's cursor; advance cursor."""
    assert _DB is not None, "bus.init() not called"
    register_subscriber(subscriber_id)

    con = sqlite3.connect(_DB)
    con.row_factory = sqlite3.Row
    cursor_row = con.execute(
        "SELECT last_event_id FROM subscriber_cursors WHERE subscriber_id=?",
        (subscriber_id,),
    ).fetchone()
    last_id = int(cursor_row["last_event_id"]) if cursor_row else 0

    rows = con.execute(
        "SELECT id, ts, topic, type, payload FROM events WHERE id > ? ORDER BY id LIMIT ?",
        (last_id, limit),
    ).fetchall()

    if rows:
        new_last = rows[-1]["id"]
        con.execute(
            """
            UPDATE subscriber_cursors
            SET last_event_id=?, updated_at=?
            WHERE subscriber_id=?
            """,
            (new_last, datetime.now(UTC).isoformat(), subscriber_id),
        )
        con.commit()
    con.close()

    return [
        {
            "id": r["id"],
            "ts": r["ts"],
            "topic": r["topic"],
            "type": r["type"],
            **json.loads(r["payload"]),
        }
        for r in rows
    ]
