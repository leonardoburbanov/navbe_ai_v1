"""SQLAlchemy control-plane models for the Navbe hub."""

from __future__ import annotations

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
    process_slug: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    watermark_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectorModel(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="langfuse")
    name: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    public_key: Mapped[str] = mapped_column(String, nullable=False)
    secret_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="untested")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DestinationModel(Base):
    __tablename__ = "destinations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # "csv_file" | "duckdb"
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
    output: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


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
        if "watermark_at" not in cols:
            conn.execute(text("ALTER TABLE workflows ADD COLUMN watermark_at DATETIME"))
        run_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(workflow_runs)")).fetchall()
        }
        if "control" not in run_cols:
            conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN control VARCHAR"))


def get_db():
    """Yield a SQLAlchemy session for FastAPI Depends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
