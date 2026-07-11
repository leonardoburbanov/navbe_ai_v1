import json
from datetime import datetime

from navbe_notify import bus as events
from navbe_scheduler.scheduler import APSchedulerAdapter, ScheduleParser

from navbe_core.graph import build_graph
from navbe_core.models import SessionLocal, WorkflowModel
from navbe_core.query import DEFAULT_PAGE_SIZE, query_destination
from navbe_core.repository import WorkflowRepository
from navbe_core.sources import SOURCES, match_source, render_markdown


class WorkflowAgent:
    def __init__(self, repo: WorkflowRepository, scheduler: APSchedulerAdapter):
        self.repo = repo
        self.scheduler = scheduler

    def schedule(
        self,
        user_id: str,
        name: str,
        task: str,
        when: str,
        context: dict,
        agent_id: str | None = None,
    ) -> WorkflowModel:
        scheduled_at = ScheduleParser.parse(when)
        is_recurring = ScheduleParser.is_cron(when)

        workflow = self.repo.create_workflow(
            user_id=user_id,
            name=name,
            task=task,
            scheduled_at=scheduled_at,
            context=context,
            cron_expression=when if is_recurring else None,
            agent_id=agent_id,
        )
        self.scheduler.register(workflow.id, scheduled_at, self._on_fire)
        return workflow

    def create_langfuse_export_workflow(
        self,
        user_id: str,
        name: str,
        connector_id: str,
        destination_id: str,
        when: str = "+5s",
        include_observations: bool = False,
    ) -> WorkflowModel:
        connector = self.repo.get_connector(connector_id, user_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        destination = self.repo.get_destination(destination_id, user_id)
        if destination is None:
            raise ValueError(f"Destination not found: {destination_id}")

        limit = 10 if include_observations else 50
        obs_note = " (with observations)" if include_observations else ""
        return self.schedule(
            user_id=user_id,
            name=name,
            task=f"Export the last {limit} Langfuse traces{obs_note} from '{connector.name}' to '{destination.name}'",
            when=when,
            context={
                "action": "graph",
                "graph": SOURCES["langfuse"]["graph"],
                "input": {
                    "connector_id": connector.id,
                    "destination_id": destination.id,
                    "limit": limit,
                    "include_observations": include_observations,
                },
            },
        )

    def suggest(self, user_id: str, hint: str) -> dict:
        """Propose a DAG workflow for a data source named in free text (e.g.
        "I want to monitor langfuse traces"), using this backend's per-source
        knowledge (sources.py) for the recommended steps/destination/dedup
        strategy. Read-only — the client confirms with a normal
        `schedule_workflow(context=..., when=...)` call once happy with it.
        """
        source_key = match_source(hint)
        if source_key is None:
            known = ", ".join(SOURCES.keys())
            raise ValueError(f"No known data source matches {hint!r}. Known sources: {known}")
        meta = SOURCES[source_key]

        connectors = [
            c for c in self.repo.list_connectors(user_id) if c.type == meta["connector_type"]
        ]
        connector = connectors[0] if connectors else None
        destinations = [
            d
            for d in self.repo.list_destinations(user_id)
            if d.type == meta["recommended_destination_type"]
        ]
        destination = destinations[0] if destinations else None

        markdown = render_markdown(
            source_key,
            connector_name=connector.name if connector else None,
            destination_name=destination.name if destination else None,
        )

        context: dict | None = None
        if connector is not None and destination is not None:
            context = {
                "action": "graph",
                "graph": meta["graph"],
                "input": {
                    **meta["default_input"],
                    "connector_id": connector.id,
                    "destination_id": destination.id,
                },
            }

        return {
            "source": source_key,
            "markdown": markdown,
            "connector_id": connector.id if connector else None,
            "destination_id": destination.id if destination else None,
            "context": context,
            "ready_to_schedule": context is not None,
        }

    def recall(self, workflow_id: str, user_id: str) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        last_run = self.repo.get_last_run(workflow_id)
        return {
            "workflow": workflow,
            "last_run": last_run,
            "context": json.loads(workflow.context),
        }

    def list(self, user_id: str) -> list[WorkflowModel]:
        return self.repo.list_workflows(user_id)

    def list_runs(self, workflow_id: str, user_id: str, page: int = 1, page_size: int = 20) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
        total = self.repo.count_runs(workflow_id)
        runs = self.repo.list_runs(workflow_id, limit=page_size, offset=(page - 1) * page_size)
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "runs": [
                {
                    "run_id": r.id,
                    "status": r.status,
                    "started_at": r.started_at.isoformat(),
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "output": json.loads(r.output) if r.output else None,
                    "error": r.error,
                }
                for r in runs
            ],
        }

    def query_workflow_destination(
        self,
        workflow_id: str,
        user_id: str,
        sql: str,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict:
        """Run a read-only SQL SELECT against the destination a workflow writes
        its traces to. Resolves destination type/config from the workflow's own
        context, so callers only need a workflow_id, not its destination_id or
        whether it's backed by duckdb or csv_file.
        """
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        destination_id = json.loads(workflow.context).get("destination_id")
        if not destination_id:
            raise ValueError(f"Workflow has no destination to query: {workflow_id}")

        destination = self.repo.get_destination(destination_id, user_id)
        if destination is None:
            raise ValueError(f"Destination not found: {destination_id}")

        return query_destination(
            destination.type, json.loads(destination.config), sql, page=page, page_size=page_size
        )

    def run_now(self, workflow_id: str, user_id: str, mode: str = "append") -> dict:
        """Run a workflow immediately, outside its schedule.

        mode="append" (default) writes new traces without duplicating ones
        already at the destination; mode="overwrite" replaces them.
        """
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        run = self.repo.start_run(workflow_id)
        events.publish({"type": "run_started", "workflow_id": workflow_id, "run_id": run.id})
        try:
            output = self._execute(workflow, self.repo, mode=mode)
            self.repo.complete_run(run.id, output)
            events.publish(
                {
                    "type": "run_completed",
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "output": output,
                }
            )
            return {"run_id": run.id, "status": "completed", "output": output}
        except Exception as e:
            self.repo.fail_run(run.id, str(e))
            events.publish(
                {
                    "type": "run_failed",
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "error": str(e),
                }
            )
            raise

    def _execute(
        self, workflow: WorkflowModel, repo: WorkflowRepository, mode: str = "append"
    ) -> dict:
        """Produce this workflow's run output. Most workflows are generic
        (AI-agent tasks with no real side effect here); `graph` DAG
        workflows (langfuse export included) are the one action this
        backend actually executes, via LangGraph steps (steps.py).
        """
        context = json.loads(workflow.context)
        if context.get("action") == "graph":
            initial = self._resolve_graph_input(context.get("input", {}), repo, workflow.user_id)
            compiled = build_graph(context["graph"])
            state = {**initial, "workflow_id": workflow.id, "mode": mode}
            for update in compiled.stream(state, stream_mode="updates"):
                for step_name, step_state in update.items():
                    state = step_state
                    events.publish(
                        {"type": "step_completed", "workflow_id": workflow.id, "step": step_name}
                    )
            return state

        return {
            "message": f"Executed: {workflow.task_description}",
            "fired_at": datetime.utcnow().isoformat(),
        }

    def _resolve_graph_input(self, input_: dict, repo: WorkflowRepository, user_id: str) -> dict:
        """Turn connector_id/destination_id references into the credentials/config
        graph steps need, resolved fresh from the DB at run time. Keeps secrets
        out of `workflow.context` — only ids are ever persisted or handed back
        through a tool response.
        """
        resolved = dict(input_)
        connector_id = resolved.pop("connector_id", None)
        if connector_id is not None:
            connector = repo.get_connector(connector_id, user_id)
            if connector is None:
                raise ValueError(f"Connector not found: {connector_id}")
            resolved.update(
                host=connector.host,
                public_key=connector.public_key,
                secret_key=connector.secret_key,
            )

        destination_id = resolved.pop("destination_id", None)
        if destination_id is not None:
            destination = repo.get_destination(destination_id, user_id)
            if destination is None:
                raise ValueError(f"Destination not found: {destination_id}")
            resolved.update(dest_type=destination.type, dest_config=json.loads(destination.config))

        return resolved

    def _on_fire(self, workflow_id: str) -> None:
        """Called by APScheduler when a workflow's scheduled time arrives."""
        db = SessionLocal()
        repo = WorkflowRepository(db)
        run = repo.start_run(workflow_id)
        events.publish({"type": "run_started", "workflow_id": workflow_id, "run_id": run.id})
        try:
            workflow = repo.get_workflow(workflow_id, user_id=None)
            if workflow is None:
                raise ValueError(f"Workflow not found: {workflow_id}")
            output = self._execute(workflow, repo)
            repo.complete_run(run.id, output)
            events.publish(
                {
                    "type": "run_completed",
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "output": output,
                }
            )

            if workflow.cron_expression and ScheduleParser.is_cron(workflow.cron_expression):
                next_run = ScheduleParser.parse(workflow.cron_expression)
                repo.reschedule_workflow(workflow_id, next_run)
                self.scheduler.register(workflow_id, next_run, self._on_fire)
                events.publish(
                    {"type": "workflow_status", "workflow_id": workflow_id, "status": "scheduled"}
                )
            else:
                repo.update_workflow_status(workflow_id, "completed")
                events.publish(
                    {"type": "workflow_status", "workflow_id": workflow_id, "status": "completed"}
                )
        except Exception as e:
            repo.fail_run(run.id, str(e))
            repo.update_workflow_status(workflow_id, "failed")
            events.publish(
                {
                    "type": "run_failed",
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "error": str(e),
                }
            )
            events.publish(
                {"type": "workflow_status", "workflow_id": workflow_id, "status": "failed"}
            )
        finally:
            db.close()
