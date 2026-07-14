import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from navbe_core.models import (
    ConnectorEnvironmentModel,
    ConnectorModel,
    ConnectorSyncModel,
    DestinationModel,
    UserModel,
    WorkflowModel,
    WorkflowRunModel,
    WorkflowRunStepModel,
)
from navbe_core.secrets import decrypt_json, encrypt_json


class WorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    # -- users ---------------------------------------------------------

    def create_user(self, email: str) -> UserModel:
        user = UserModel(email=email)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_user_by_api_key(self, api_key: str) -> UserModel | None:
        return self.db.query(UserModel).filter(UserModel.api_key == api_key).first()

    # -- workflows -------------------------------------------------------

    def create_workflow(
        self,
        user_id: str,
        name: str,
        task: str,
        scheduled_at: datetime,
        context: dict,
        cron_expression: str | None = None,
        agent_id: str | None = None,
        process_slug: str | None = None,
        slug: str | None = None,
    ) -> WorkflowModel:
        friendly = slug or process_slug
        if friendly and self.slug_taken(user_id, friendly):
            raise ValueError(f"Workflow slug already in use: {friendly}")
        workflow = WorkflowModel(
            user_id=user_id,
            agent_id=agent_id or str(uuid.uuid4()),
            name=name,
            task_description=task,
            scheduled_at=scheduled_at,
            context=json.dumps(context),
            cron_expression=cron_expression,
            # ponytail: dual-write one sprint
            process_slug=friendly,
            slug=friendly,
        )
        self.db.add(workflow)
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def slug_taken(
        self, user_id: str, slug: str, *, exclude_workflow_id: str | None = None
    ) -> bool:
        """True if another non-archived workflow for this user already owns the slug."""
        q = self.db.query(WorkflowModel).filter(
            WorkflowModel.user_id == user_id,
            WorkflowModel.status != "archived",
            (WorkflowModel.slug == slug) | (WorkflowModel.process_slug == slug),
        )
        if exclude_workflow_id:
            q = q.filter(WorkflowModel.id != exclude_workflow_id)
        return q.first() is not None

    def get_workflow(self, workflow_id: str, user_id: str | None = None) -> WorkflowModel | None:
        query = self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id)
        if user_id is not None:
            query = query.filter(WorkflowModel.user_id == user_id)
        return query.first()

    def get_workflow_by_slug(self, slug: str) -> WorkflowModel | None:
        """Return the workflow for a friendly slug (checks slug and legacy process_slug)."""
        return (
            self.db.query(WorkflowModel)
            .filter(
                (WorkflowModel.slug == slug) | (WorkflowModel.process_slug == slug),
                WorkflowModel.status != "archived",
            )
            .order_by(WorkflowModel.created_at.desc())
            .first()
        )

    def list_workflows_with_slug(self, user_id: str) -> list[WorkflowModel]:
        """List named (non-archived) workflows that have a slug."""
        return (
            self.db.query(WorkflowModel)
            .filter(
                WorkflowModel.user_id == user_id,
                WorkflowModel.status != "archived",
                (WorkflowModel.slug.isnot(None)) | (WorkflowModel.process_slug.isnot(None)),
            )
            .order_by(WorkflowModel.created_at.desc())
            .all()
        )

    def list_workflows(self, user_id: str, *, include_archived: bool = False) -> list[WorkflowModel]:
        q = self.db.query(WorkflowModel).filter(WorkflowModel.user_id == user_id)
        if not include_archived:
            q = q.filter(WorkflowModel.status != "archived")
        return q.order_by(WorkflowModel.created_at.desc()).all()

    def update_workflow_fields(self, workflow_id: str, **fields: object) -> WorkflowModel | None:
        """Patch arbitrary workflow columns; dual-sync slug/process_slug when either set."""
        if "slug" in fields and "process_slug" not in fields:
            fields["process_slug"] = fields["slug"]
        if "process_slug" in fields and "slug" not in fields:
            fields["slug"] = fields["process_slug"]
        self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).update(fields)
        self.db.commit()
        return self.get_workflow(workflow_id)

    def update_workflow_context(self, workflow_id: str, context: dict) -> None:
        """Replace persisted Workflow IR JSON."""
        self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).update(
            {"context": json.dumps(context)}
        )
        self.db.commit()


    def get_due_workflows(self) -> list[WorkflowModel]:
        return (
            self.db.query(WorkflowModel)
            .filter(WorkflowModel.status == "scheduled")
            .filter(WorkflowModel.scheduled_at <= datetime.utcnow())
            .all()
        )

    def get_scheduled_workflows(self) -> list[WorkflowModel]:
        return self.db.query(WorkflowModel).filter(WorkflowModel.status == "scheduled").all()

    def update_workflow_status(self, workflow_id: str, status: str) -> None:
        self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).update(
            {"status": status}
        )
        self.db.commit()

    def reschedule_workflow(self, workflow_id: str, scheduled_at: datetime) -> None:
        self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).update(
            {"status": "scheduled", "scheduled_at": scheduled_at}
        )
        self.db.commit()

    def update_workflow_watermark(self, workflow_id: str, watermark: datetime) -> None:
        """Advance the incremental extract watermark after a successful run."""
        self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id).update(
            {"watermark_at": watermark}
        )
        self.db.commit()

    # -- runs ------------------------------------------------------------

    @staticmethod
    def _elapsed_ms(started_at: datetime | None, ended_at: datetime | None = None) -> int | None:
        """Wall-clock duration in ms from started_at to ended_at (or now)."""
        if started_at is None:
            return None
        end = ended_at or datetime.utcnow()
        # Naive UTC both sides (control plane stores utcnow)
        delta = end - started_at
        return max(0, int(delta.total_seconds() * 1000))

    def start_run(self, workflow_id: str) -> WorkflowRunModel:
        run = WorkflowRunModel(workflow_id=workflow_id, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def complete_run(self, run_id: str, output: dict) -> None:
        run = self.get_run(run_id)
        completed = datetime.utcnow()
        duration_ms = self._elapsed_ms(run.started_at if run else None, completed)
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(
            {
                "status": "completed",
                "completed_at": completed,
                "duration_ms": duration_ms,
                "output": json.dumps(output),
                "control": None,
            }
        )
        self.db.commit()

    def fail_run(self, run_id: str, error: str) -> None:
        run = self.get_run(run_id)
        completed = datetime.utcnow()
        duration_ms = self._elapsed_ms(run.started_at if run else None, completed)
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(
            {
                "status": "failed",
                "completed_at": completed,
                "duration_ms": duration_ms,
                "error": error,
                "control": None,
            }
        )
        self.db.commit()

    def get_run(self, run_id: str) -> WorkflowRunModel | None:
        return self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).first()

    def set_run_control(self, run_id: str, control: str | None) -> WorkflowRunModel | None:
        """Request pause/cancel (or clear). Returns the run if found."""
        run = self.get_run(run_id)
        if run is None:
            return None
        run.control = control
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_run_paused(self, run_id: str, output: dict) -> None:
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(
            {
                "status": "paused",
                "control": None,
                "output": json.dumps(output),
            }
        )
        self.db.commit()

    def mark_run_cancelled(self, run_id: str, output: dict | None = None) -> None:
        run = self.get_run(run_id)
        completed = datetime.utcnow()
        payload: dict = {
            "status": "cancelled",
            "completed_at": completed,
            "duration_ms": self._elapsed_ms(run.started_at if run else None, completed),
            "control": None,
            "error": "cancelled by user",
        }
        if output is not None:
            payload["output"] = json.dumps(output)
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(payload)
        self.db.commit()

    def mark_run_running(self, run_id: str) -> None:
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(
            {"status": "running", "control": None}
        )
        self.db.commit()

    def record_run_step(
        self,
        run_id: str,
        step_id: str,
        *,
        status: str = "succeeded",
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        attempt: int = 1,
    ) -> WorkflowRunStepModel:
        """Insert a finished step timing row for a run."""
        done = completed_at or datetime.utcnow()
        start = started_at
        if start is None and duration_ms is not None:
            from datetime import timedelta

            start = done - timedelta(milliseconds=max(0, duration_ms))
        row = WorkflowRunStepModel(
            run_id=run_id,
            step_id=step_id,
            attempt=attempt,
            status=status,
            started_at=start,
            completed_at=done,
            duration_ms=duration_ms,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_run_steps(self, run_id: str) -> list[WorkflowRunStepModel]:
        return (
            self.db.query(WorkflowRunStepModel)
            .filter(WorkflowRunStepModel.run_id == run_id)
            .order_by(WorkflowRunStepModel.completed_at.asc(), WorkflowRunStepModel.step_id)
            .all()
        )

    def serialize_run_steps(self, run_id: str) -> list[dict]:
        """API/MCP shape for per-step timings."""
        return [
            {
                "id": s.step_id,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "attempt": s.attempt,
            }
            for s in self.list_run_steps(run_id)
        ]

    def get_last_run(self, workflow_id: str) -> WorkflowRunModel | None:
        return (
            self.db.query(WorkflowRunModel)
            .filter(WorkflowRunModel.workflow_id == workflow_id)
            .order_by(WorkflowRunModel.started_at.desc())
            .first()
        )

    def list_runs(self, workflow_id: str, limit: int, offset: int) -> list[WorkflowRunModel]:
        return (
            self.db.query(WorkflowRunModel)
            .filter(WorkflowRunModel.workflow_id == workflow_id)
            .order_by(WorkflowRunModel.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_runs(self, workflow_id: str) -> int:
        return (
            self.db.query(WorkflowRunModel)
            .filter(WorkflowRunModel.workflow_id == workflow_id)
            .count()
        )

    def list_running_runs(self, limit: int = 20) -> list[WorkflowRunModel]:
        """In-flight runs for Control UI live strip hydrate."""
        return (
            self.db.query(WorkflowRunModel)
            .filter(WorkflowRunModel.status.in_(("running", "paused")))
            .order_by(WorkflowRunModel.started_at.desc())
            .limit(limit)
            .all()
        )

    def list_runs_for_user(
        self,
        user_id: str,
        process_slug: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[WorkflowRunModel, WorkflowModel]], int]:
        """Cross-process runs for the Runs-first UI. Returns [(run, workflow), total]."""
        q = (
            self.db.query(WorkflowRunModel, WorkflowModel)
            .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
            .filter(WorkflowModel.user_id == user_id)
        )
        if process_slug:
            q = q.filter(
                (WorkflowModel.slug == process_slug)
                | (WorkflowModel.process_slug == process_slug)
            )
        total = q.count()
        rows = (
            q.order_by(WorkflowRunModel.started_at.desc()).offset(offset).limit(limit).all()
        )
        return rows, total

    # -- connectors --------------------------------------------------------

    def create_connector(
        self,
        user_id: str,
        name: str,
        host: str = "",
        public_key: str = "",
        secret_key: str = "",
        type: str = "langfuse",
        *,
        env_key: str = "prod",
        public_config: dict | None = None,
        secrets: dict | None = None,
    ) -> ConnectorModel:
        """Create a source connector and an initial environment pack."""
        host_val = host or (public_config or {}).get("host", "") or ""
        pk = public_key or (secrets or {}).get("public_key", "") or ""
        sk = secret_key or (secrets or {}).get("secret_key", "") or ""
        connector = ConnectorModel(
            user_id=user_id,
            type=type,
            name=name,
            host=host_val,
            public_key=pk,
            secret_key=sk,
        )
        self.db.add(connector)
        self.db.flush()
        pc = dict(public_config or {})
        if host_val and "host" not in pc:
            pc["host"] = host_val
        sec = dict(secrets or {})
        if pk and "public_key" not in sec:
            sec["public_key"] = pk
        if sk and "secret_key" not in sec:
            sec["secret_key"] = sk
        if pc or sec:
            self._upsert_env_row(
                connector.id,
                env_key=env_key,
                public_config=pc,
                secrets=sec,
                is_default=True,
                label=env_key.title(),
            )
        self.db.commit()
        self.db.refresh(connector)
        return connector

    def update_connector(
        self, connector_id: str, user_id: str, *, name: str | None = None, status: str | None = None
    ) -> ConnectorModel | None:
        connector = self.get_connector(connector_id, user_id)
        if connector is None:
            return None
        if name is not None:
            connector.name = name
        if status is not None:
            connector.status = status
        self.db.commit()
        self.db.refresh(connector)
        return connector

    def list_connectors(self, user_id: str) -> list[ConnectorModel]:
        return (
            self.db.query(ConnectorModel)
            .filter(ConnectorModel.user_id == user_id)
            .order_by(ConnectorModel.created_at.desc())
            .all()
        )

    def get_connector(self, connector_id: str, user_id: str) -> ConnectorModel | None:
        return (
            self.db.query(ConnectorModel)
            .filter(ConnectorModel.id == connector_id, ConnectorModel.user_id == user_id)
            .first()
        )

    def update_connector_status(self, connector_id: str, status: str) -> None:
        self.db.query(ConnectorModel).filter(ConnectorModel.id == connector_id).update(
            {"status": status}
        )
        self.db.commit()

    def delete_connector(self, connector_id: str, user_id: str) -> bool:
        connector = self.get_connector(connector_id, user_id)
        if connector is None:
            return False
        self.db.query(ConnectorEnvironmentModel).filter(
            ConnectorEnvironmentModel.connector_id == connector_id
        ).delete()
        self.db.query(ConnectorSyncModel).filter(
            ConnectorSyncModel.connector_id == connector_id
        ).delete()
        self.db.delete(connector)
        self.db.commit()
        return True

    def _upsert_env_row(
        self,
        connector_id: str,
        *,
        env_key: str,
        public_config: dict,
        secrets: dict | None,
        is_default: bool = False,
        label: str | None = None,
        status: str = "untested",
    ) -> ConnectorEnvironmentModel:
        row = (
            self.db.query(ConnectorEnvironmentModel)
            .filter(
                ConnectorEnvironmentModel.connector_id == connector_id,
                ConnectorEnvironmentModel.env_key == env_key,
            )
            .first()
        )
        if is_default:
            self.db.query(ConnectorEnvironmentModel).filter(
                ConnectorEnvironmentModel.connector_id == connector_id
            ).update({"is_default": "0"})
        if row is None:
            row = ConnectorEnvironmentModel(
                connector_id=connector_id,
                env_key=env_key,
                label=label or env_key,
                public_config=json.dumps(public_config),
                secrets_enc=encrypt_json(secrets or {}),
                is_default="1" if is_default else "0",
                status=status,
            )
            self.db.add(row)
        else:
            row.public_config = json.dumps(public_config)
            if secrets is not None:
                # Merge: only replace keys provided (allow rotate without wiping)
                existing = decrypt_json(row.secrets_enc) if row.secrets_enc else {}
                existing.update({k: v for k, v in secrets.items() if v})
                row.secrets_enc = encrypt_json(existing)
            if label is not None:
                row.label = label
            if is_default:
                row.is_default = "1"
            row.status = status
            row.updated_at = datetime.utcnow()
        return row

    def upsert_connector_env(
        self,
        connector_id: str,
        user_id: str,
        env_key: str,
        *,
        public_config: dict | None = None,
        secrets: dict | None = None,
        is_default: bool = False,
        label: str | None = None,
    ) -> ConnectorEnvironmentModel:
        connector = self.get_connector(connector_id, user_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        row = self._upsert_env_row(
            connector_id,
            env_key=env_key,
            public_config=public_config or {},
            secrets=secrets,
            is_default=is_default
            or not self.list_connector_envs(connector_id),
            label=label,
        )
        # Dual-write default env onto legacy columns for old readers
        if row.is_default == "1":
            pc = json.loads(row.public_config or "{}")
            sec = decrypt_json(row.secrets_enc)
            connector.host = pc.get("host") or connector.host
            connector.public_key = sec.get("public_key") or connector.public_key
            connector.secret_key = sec.get("secret_key") or connector.secret_key
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_connector_envs(self, connector_id: str) -> list[ConnectorEnvironmentModel]:
        return (
            self.db.query(ConnectorEnvironmentModel)
            .filter(ConnectorEnvironmentModel.connector_id == connector_id)
            .order_by(ConnectorEnvironmentModel.env_key)
            .all()
        )

    def get_connector_env(
        self, connector_id: str, env_key: str | None = None
    ) -> ConnectorEnvironmentModel | None:
        q = self.db.query(ConnectorEnvironmentModel).filter(
            ConnectorEnvironmentModel.connector_id == connector_id
        )
        if env_key:
            return q.filter(ConnectorEnvironmentModel.env_key == env_key).first()
        return (
            q.filter(ConnectorEnvironmentModel.is_default == "1").first()
            or q.order_by(ConnectorEnvironmentModel.created_at).first()
        )

    def delete_connector_env(self, connector_id: str, user_id: str, env_key: str) -> bool:
        connector = self.get_connector(connector_id, user_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        envs = self.list_connector_envs(connector_id)
        if len(envs) <= 1:
            raise ValueError("Cannot delete the last environment on a connector")
        row = self.get_connector_env(connector_id, env_key)
        if row is None:
            return False
        was_default = row.is_default == "1"
        self.db.delete(row)
        if was_default:
            remaining = self.list_connector_envs(connector_id)
            if remaining:
                remaining[0].is_default = "1"
        self.db.commit()
        return True

    def resolve_connector_credentials(
        self,
        connector_id: str,
        user_id: str,
        env_key: str | None = None,
    ) -> dict:
        """Return host/public_key/secret_key (+ public_config) for runtime.

        Prefers ConnectorEnvironment; falls back to legacy connector columns.
        """
        connector = self.get_connector(connector_id, user_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        env = self.get_connector_env(connector_id, env_key)
        if env is not None:
            pc = json.loads(env.public_config or "{}")
            sec = decrypt_json(env.secrets_enc)
            return {
                "host": pc.get("host") or connector.host,
                "public_key": sec.get("public_key") or connector.public_key,
                "secret_key": sec.get("secret_key") or connector.secret_key,
                "public_config": pc,
                "env_key": env.env_key,
            }
        return {
            "host": connector.host,
            "public_key": connector.public_key,
            "secret_key": connector.secret_key,
            "public_config": {"host": connector.host},
            "env_key": env_key or "prod",
        }

    def env_summary(self, connector_id: str) -> list[dict]:
        """Redacted env list for API/MCP."""
        out = []
        for e in self.list_connector_envs(connector_id):
            pc = json.loads(e.public_config or "{}")
            sec = decrypt_json(e.secrets_enc) if e.secrets_enc else {}
            out.append(
                {
                    "env_key": e.env_key,
                    "label": e.label,
                    "is_default": e.is_default == "1",
                    "status": e.status,
                    "public_config": pc,
                    "has_secrets": bool(sec),
                }
            )
        return out

    # -- connector syncs -----------------------------------------------------

    def start_connector_sync(self, connector_id: str) -> ConnectorSyncModel:
        sync = ConnectorSyncModel(connector_id=connector_id, status="running")
        self.db.add(sync)
        self.db.commit()
        self.db.refresh(sync)
        return sync

    def complete_connector_sync(self, sync_id: str, traces: list[dict]) -> None:
        self.db.query(ConnectorSyncModel).filter(ConnectorSyncModel.id == sync_id).update(
            {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "trace_count": len(traces),
                "output": json.dumps(traces),
            }
        )
        self.db.commit()

    def fail_connector_sync(self, sync_id: str, error: str) -> None:
        self.db.query(ConnectorSyncModel).filter(ConnectorSyncModel.id == sync_id).update(
            {
                "status": "failed",
                "completed_at": datetime.utcnow(),
                "error": error,
            }
        )
        self.db.commit()

    def list_connector_syncs(self, connector_id: str) -> list[ConnectorSyncModel]:
        return (
            self.db.query(ConnectorSyncModel)
            .filter(ConnectorSyncModel.connector_id == connector_id)
            .order_by(ConnectorSyncModel.started_at.desc())
            .all()
        )

    # -- destinations --------------------------------------------------------

    def create_destination(
        self, user_id: str, type: str, name: str, config: dict
    ) -> DestinationModel:
        destination = DestinationModel(
            user_id=user_id, type=type, name=name, config=json.dumps(config)
        )
        self.db.add(destination)
        self.db.commit()
        self.db.refresh(destination)
        return destination

    def list_destinations(self, user_id: str) -> list[DestinationModel]:
        return (
            self.db.query(DestinationModel)
            .filter(DestinationModel.user_id == user_id)
            .order_by(DestinationModel.created_at.desc())
            .all()
        )

    def get_destination(self, destination_id: str, user_id: str) -> DestinationModel | None:
        return (
            self.db.query(DestinationModel)
            .filter(DestinationModel.id == destination_id, DestinationModel.user_id == user_id)
            .first()
        )

    def delete_destination(self, destination_id: str, user_id: str) -> bool:
        deleted = (
            self.db.query(DestinationModel)
            .filter(DestinationModel.id == destination_id, DestinationModel.user_id == user_id)
            .delete()
        )
        self.db.commit()
        return deleted > 0
