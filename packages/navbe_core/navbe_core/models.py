"""SQLAlchemy control-plane models for the Navbe hub."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from navbe_core.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for control-plane tables."""


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    api_key: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, default=lambda: "nvb_" + uuid.uuid4().hex[:16]
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowModel(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    task_description: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String, nullable=True)
    context: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    # ponytail: process_slug kept one sprint for dual-read; prefer slug
    process_slug: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    watermark_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def friendly_slug(self) -> str | None:
        """Canonical workflow slug (falls back to legacy process_slug)."""
        return self.slug or self.process_slug


class ConnectorModel(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="langfuse")
    name: Mapped[str] = mapped_column(String, nullable=False)
    # ponytail: legacy columns dual-read one sprint; prefer ConnectorEnvironment
    host: Mapped[str] = mapped_column(String, nullable=False, default="")
    public_key: Mapped[str] = mapped_column(String, nullable=False, default="")
    secret_key: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="untested")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectorEnvironmentModel(Base):
    """Per-connector credential pack (staging / testing / prod / custom)."""

    __tablename__ = "connector_environments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    connector_id: Mapped[str] = mapped_column(
        String, ForeignKey("connectors.id"), nullable=False, index=True
    )
    env_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    public_config: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    secrets_enc: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_default: Mapped[str] = mapped_column(String, nullable=False, default="0")  # "0"|"1"
    status: Mapped[str] = mapped_column(String, nullable=False, default="untested")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DestinationModel(Base):
    __tablename__ = "destinations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # duckdb | sqlite | email | …
    name: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(String, ForeignKey("workflows.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    # ponytail: cooperative pause/cancel between steps — null | pause_requested | cancel_requested
    control: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Sprint 11: wall-clock duration; null while running / unknown
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class WorkflowRunStepModel(Base):
    """Per-step timing for one workflow run (Sprint 11)."""

    __tablename__ = "workflow_run_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="succeeded")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConnectorSyncModel(Base):
    __tablename__ = "connector_syncs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    connector_id: Mapped[str] = mapped_column(String, ForeignKey("connectors.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    trace_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def init_db() -> None:
    """Create ORM tables, schema_version, and additive column migrations."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
        )
        # Additive columns for Sprint 1 (SQLite create_all does not ALTER)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(workflows)")).fetchall()}
        if "process_slug" not in cols:
            conn.execute(text("ALTER TABLE workflows ADD COLUMN process_slug VARCHAR"))
        if "slug" not in cols:
            conn.execute(text("ALTER TABLE workflows ADD COLUMN slug VARCHAR"))
            # Backfill from legacy process_slug
            conn.execute(
                text("UPDATE workflows SET slug = process_slug WHERE slug IS NULL AND process_slug IS NOT NULL")
            )
        if "watermark_at" not in cols:
            conn.execute(text("ALTER TABLE workflows ADD COLUMN watermark_at DATETIME"))
        run_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(workflow_runs)")).fetchall()
        }
        if "control" not in run_cols:
            conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN control VARCHAR"))
        if "duration_ms" not in run_cols:
            conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN duration_ms INTEGER"))
            # Best-effort run totals from timestamps only (no per-step history)
            conn.execute(
                text(
                    """
                    UPDATE workflow_runs
                    SET duration_ms = CAST(
                        (julianday(completed_at) - julianday(started_at)) * 86400000 AS INTEGER
                    )
                    WHERE duration_ms IS NULL
                      AND completed_at IS NOT NULL
                      AND started_at IS NOT NULL
                    """
                )
            )
        # Sprint 10: backfill connector_environments from flat connector columns
        _migrate_connector_environments(conn)


def _migrate_connector_environments(conn) -> None:
    """Create env rows from legacy host/public_key/secret_key when missing."""
    from navbe_core.secrets import encrypt

    tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    if "connector_environments" not in tables:
        return  # create_all should have made it; nothing to backfill yet
    rows = conn.execute(
        text("SELECT id, host, public_key, secret_key FROM connectors")
    ).fetchall()
    for cid, host, pk, sk in rows:
        exists = conn.execute(
            text(
                "SELECT 1 FROM connector_environments WHERE connector_id = :cid LIMIT 1"
            ),
            {"cid": cid},
        ).fetchone()
        if exists:
            continue
        if not (host or pk or sk):
            continue
        public_config = json.dumps({"host": host or ""})
        secrets_enc = encrypt(json.dumps({"public_key": pk or "", "secret_key": sk or ""}))
        conn.execute(
            text(
                """
                INSERT INTO connector_environments
                (id, connector_id, env_key, label, public_config, secrets_enc, is_default, status, created_at, updated_at)
                VALUES (:id, :cid, 'prod', 'Production', :pc, :se, '1', 'untested', :ts, :ts)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "cid": cid,
                "pc": public_config,
                "se": secrets_enc,
                "ts": datetime.utcnow().isoformat(),
            },
        )


def get_db():
    """Yield a SQLAlchemy session for FastAPI Depends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
