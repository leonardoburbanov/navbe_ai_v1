import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from navbe_core.models import (
    ConnectorModel,
    ConnectorSyncModel,
    DestinationModel,
    UserModel,
    WorkflowModel,
    WorkflowRunModel,
)


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
    ) -> WorkflowModel:
        workflow = WorkflowModel(
            user_id=user_id,
            agent_id=agent_id or str(uuid.uuid4()),
            name=name,
            task_description=task,
            scheduled_at=scheduled_at,
            context=json.dumps(context),
            cron_expression=cron_expression,
        )
        self.db.add(workflow)
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def get_workflow(self, workflow_id: str, user_id: str | None = None) -> WorkflowModel | None:
        query = self.db.query(WorkflowModel).filter(WorkflowModel.id == workflow_id)
        if user_id is not None:
            query = query.filter(WorkflowModel.user_id == user_id)
        return query.first()

    def list_workflows(self, user_id: str) -> list[WorkflowModel]:
        return (
            self.db.query(WorkflowModel)
            .filter(WorkflowModel.user_id == user_id)
            .order_by(WorkflowModel.created_at.desc())
            .all()
        )

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

    # -- runs ------------------------------------------------------------

    def start_run(self, workflow_id: str) -> WorkflowRunModel:
        run = WorkflowRunModel(workflow_id=workflow_id, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def complete_run(self, run_id: str, output: dict) -> None:
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(
            {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "output": json.dumps(output),
            }
        )
        self.db.commit()

    def fail_run(self, run_id: str, error: str) -> None:
        self.db.query(WorkflowRunModel).filter(WorkflowRunModel.id == run_id).update(
            {
                "status": "failed",
                "completed_at": datetime.utcnow(),
                "error": error,
            }
        )
        self.db.commit()

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

    # -- connectors --------------------------------------------------------

    def create_connector(
        self,
        user_id: str,
        name: str,
        host: str,
        public_key: str,
        secret_key: str,
        type: str = "langfuse",
    ) -> ConnectorModel:
        connector = ConnectorModel(
            user_id=user_id,
            type=type,
            name=name,
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )
        self.db.add(connector)
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
        deleted = (
            self.db.query(ConnectorModel)
            .filter(ConnectorModel.id == connector_id, ConnectorModel.user_id == user_id)
            .delete()
        )
        self.db.commit()
        return deleted > 0

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
