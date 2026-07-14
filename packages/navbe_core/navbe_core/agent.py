from __future__ import annotations

import json
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from navbe_notify import bus as events
from navbe_scheduler.scheduler import APSchedulerAdapter, ScheduleParser

from navbe_core.config import DATA_DIR
from navbe_core.graph import build_graph
from navbe_core.live_url import live_workflow_url, workflow_ui_url
from navbe_core.models import SessionLocal, WorkflowModel
from navbe_core.query import DEFAULT_PAGE_SIZE, query_destination
from navbe_core.repository import WorkflowRepository
from navbe_core.sources import SOURCES, match_source, render_markdown
from navbe_core.wiring import (
    KNOWN_STEPS,
    recompute_entry,
    resolve_step_hint,
    wire_step,
)

# ponytail: alias until callers finish rename
live_process_url = live_workflow_url


def _workflow_slug(workflow: WorkflowModel) -> str | None:
    """Canonical friendly slug for a workflow."""
    return workflow.friendly_slug() if hasattr(workflow, "friendly_slug") else (
        workflow.slug or workflow.process_slug
    )


def _slug_payload(workflow: WorkflowModel) -> dict:
    """Dual slug keys for event/API payloads (Sprint 9 compat)."""
    s = _workflow_slug(workflow)
    return {"slug": s, "process_slug": s}


def _process_topic(workflow: WorkflowModel) -> str:
    """Legacy topic (`process.{slug}`) — keep for subscribers this sprint."""
    return f"process.{_workflow_slug(workflow) or workflow.id}"


def _workflow_topic(workflow: WorkflowModel) -> str:
    """Canonical topic (`workflow.{slug}`)."""
    return f"workflow.{_workflow_slug(workflow) or workflow.id}"


def _publish_workflow_topics(
    event_type: str,
    payload: dict,
    workflow: WorkflowModel,
) -> None:
    """Dual-publish to process.* and workflow.* topics."""
    events.publish(_process_topic(workflow), event_type, payload)
    events.publish(_workflow_topic(workflow), event_type, payload)


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
        process_slug: str | None = None,
        slug: str | None = None,
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
            process_slug=process_slug,
            slug=slug or process_slug,
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
        include_observations: bool = True,
        process_slug: str = "langfuse_daily",
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
            task=(
                f"Export the last {limit} Langfuse traces{obs_note} "
                f"from '{connector.name}' to '{destination.name}'"
            ),
            when=when,
            process_slug=process_slug,
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

    def create_daily_report_workflow(
        self,
        user_id: str,
        destination_id: str,
        email_to: list[str] | str,
        when: str = "0 23 * * *",
        name: str = "langfuse_daily_report",
        process_slug: str = "langfuse_daily_report",
    ) -> WorkflowModel:
        """Schedule end-of-day HTML email report from the retailer mart."""
        destination = self.repo.get_destination(destination_id, user_id)
        if destination is None:
            raise ValueError(f"Destination not found: {destination_id}")
        if isinstance(email_to, str):
            recipients = [a.strip() for a in email_to.split(",") if a.strip()]
        else:
            recipients = list(email_to)
        if not recipients:
            raise ValueError("email_to is required")

        graph = SOURCES["langfuse_daily_report"]["graph"]
        return self.schedule(
            user_id=user_id,
            name=name,
            task=(
                f"End-of-day retailer HTML email report from '{destination.name}' "
                f"to {', '.join(recipients)}"
            ),
            when=when,
            process_slug=process_slug,
            context={
                "action": "graph",
                "graph": graph,
                "input": {
                    "destination_id": destination.id,
                    "email_to": recipients,
                },
            },
        )

    def run_daily_report_now(
        self,
        user_id: str,
        destination_id: str,
        email_to: list[str] | str | None = None,
        *,
        preview: bool = False,
    ) -> dict:
        """One-shot report via LangGraph steps (build_retailer_report → send_email_report)."""
        destination = self.repo.get_destination(destination_id, user_id)
        if destination is None:
            raise ValueError(f"Destination not found: {destination_id}")
        if isinstance(email_to, str):
            recipients = [a.strip() for a in email_to.split(",") if a.strip()]
        elif email_to:
            recipients = list(email_to)
        else:
            recipients = []
        if not preview and not recipients:
            raise ValueError("email_to is required to send")

        graph = SOURCES["langfuse_daily_report"]["graph"]
        workflow = self.repo.create_workflow(
            user_id=user_id,
            name="langfuse_daily_report_preview" if preview else "langfuse_daily_report_once",
            task=(
                f"{'Preview' if preview else 'Send'} retailer HTML report from "
                f"'{destination.name}'"
            ),
            scheduled_at=datetime.utcnow(),
            process_slug="langfuse_daily_report",
            context={
                "action": "graph",
                "graph": graph,
                "input": {
                    "destination_id": destination.id,
                    "email_to": recipients,
                    "preview_only": preview,
                },
            },
        )
        return self.run_now(workflow.id, user_id, mode="append")

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
            "draft": {
                "name": f"{meta['label']} workflow",
                "slug": source_key,
                "task": f"Monitor {meta['label']} {'/'.join(meta['entities'])}",
                "source": source_key,
                "graph": meta["graph"],
                "input": (
                    {
                        **meta["default_input"],
                        "connector_id": connector.id if connector else None,
                        "destination_id": destination.id if destination else None,
                    }
                    if connector or destination
                    else {**meta["default_input"]}
                ),
                "trigger": {"type": "manual", "cron": None, "tz": "UTC"},
            },
            "needs_input": (
                None
                if context is not None
                else {
                    "fields": [
                        f
                        for f, ok in (
                            ("connector", connector is not None),
                            ("destination", destination is not None),
                        )
                        if not ok
                    ],
                    "hint": "create_connector / create_destination then confirm_workflow",
                }
            ),
            "next_step": (
                "call confirm_workflow with this draft (and optional when=cron)"
                if context is not None
                else "create missing connector/destination, then propose again or confirm with ids"
            ),
        }

    def propose_workflow(self, user_id: str, hint: str) -> dict:
        """Alias of suggest with draft-oriented response (Sprint 9)."""
        return self.suggest(user_id, hint)

    def confirm_workflow(
        self,
        user_id: str,
        draft: dict,
        when: str = "+5s",
        name: str | None = None,
        slug: str | None = None,
    ) -> dict:
        """Persist a propose_workflow draft as a scheduled WorkflowModel."""
        graph = draft.get("graph") or (draft.get("context") or {}).get("graph")
        input_ = draft.get("input") or (draft.get("context") or {}).get("input") or {}
        if not graph:
            raise ValueError("draft.graph is required")
        connector_id = input_.get("connector_id")
        destination_id = input_.get("destination_id")
        if not connector_id or not destination_id:
            # Allow report-only graphs with destination only
            nodes = list(graph.get("nodes") or [])
            needs_connector = any(n.startswith("fetch_") for n in nodes)
            if needs_connector and not connector_id:
                raise ValueError("draft.input.connector_id is required")
            if not destination_id and "write_traces" in nodes:
                raise ValueError("draft.input.destination_id is required")

        friendly = slug or draft.get("slug") or draft.get("source") or "workflow"
        wf_name = name or draft.get("name") or friendly
        task = draft.get("task") or f"Run workflow {friendly}"
        trigger = draft.get("trigger") or {}
        cron = when if ScheduleParser.is_cron(when) else trigger.get("cron")
        when_final = cron or when

        context = {
            "action": "graph",
            "graph": graph,
            "input": {k: v for k, v in input_.items() if v is not None},
            "trigger": {
                "type": "cron" if ScheduleParser.is_cron(when_final) else "manual",
                "cron": when_final if ScheduleParser.is_cron(when_final) else None,
                "tz": trigger.get("tz") or "UTC",
                "overlap_policy": trigger.get("overlap_policy") or "run_once_catchup",
            },
        }
        workflow = self.schedule(
            user_id=user_id,
            name=wf_name,
            task=task,
            when=when_final,
            context=context,
            slug=friendly,
            process_slug=friendly,
        )
        ui = workflow_ui_url(workflow_id=workflow.id)
        return {
            "workflow_id": workflow.id,
            "slug": _workflow_slug(workflow),
            "process_slug": _workflow_slug(workflow),
            "name": workflow.name,
            "status": workflow.status,
            "graph": graph,
            "ui_url": ui,
            "live_url": live_workflow_url(workflow_id=workflow.id, page="workflows"),
            "next_step": f"Open ui_url to inspect the workflow: {ui}",
        }

    def _load_context(self, workflow: WorkflowModel) -> dict:
        return json.loads(workflow.context or "{}")

    def _mutator_result(
        self, workflow: WorkflowModel, *, next_step: str, extra: dict | None = None
    ) -> dict:
        ctx = self._load_context(workflow)
        graph = ctx.get("graph") or {}
        ui = workflow_ui_url(workflow_id=workflow.id)
        out = {
            "workflow_id": workflow.id,
            "slug": _workflow_slug(workflow),
            "process_slug": _workflow_slug(workflow),
            "graph": {
                "entry": graph.get("entry"),
                "nodes": graph.get("nodes") or [],
                "edges": graph.get("edges") or [],
            },
            "ui_url": ui,
            "next_step": next_step,
        }
        if extra:
            out.update(extra)
        return out

    def update_workflow(
        self,
        user_id: str,
        workflow_id: str,
        *,
        name: str | None = None,
        slug: str | None = None,
        task: str | None = None,
        status: str | None = None,
    ) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        fields: dict = {}
        if name is not None:
            fields["name"] = name
        if task is not None:
            fields["task_description"] = task
        if status is not None:
            fields["status"] = status
        if slug is not None:
            if self.repo.slug_taken(user_id, slug, exclude_workflow_id=workflow_id):
                raise ValueError(f"Workflow slug already in use: {slug}")
            fields["slug"] = slug
            fields["process_slug"] = slug
        if fields:
            self.repo.update_workflow_fields(workflow_id, **fields)
            workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(workflow, next_step="call get_workflow_status or open ui_url")

    def delete_workflow(self, user_id: str, workflow_id: str) -> dict:
        """Soft-archive a workflow. Refuses if a run is in progress."""
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        last = self.repo.get_last_run(workflow_id)
        if last and last.status in ("running", "paused"):
            raise ValueError(
                f"Cannot archive workflow while run {last.id} is {last.status}; stop it first"
            )
        self.repo.update_workflow_status(workflow_id, "archived")
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(
            workflow,
            next_step="workflow archived; list_workflows hides it by default",
            extra={"status": "archived"},
        )

    def set_workflow_trigger(
        self,
        user_id: str,
        workflow_id: str,
        *,
        when: str | None = None,
        hint: str | None = None,
    ) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        raw = when or hint or ""
        raw = raw.strip()
        if not raw or raw.lower() in ("manual", "mcp", "mcp_tool"):
            ctx = self._load_context(workflow)
            ctx["trigger"] = {
                "type": "manual",
                "cron": None,
                "tz": "UTC",
                "overlap_policy": "run_once_catchup",
            }
            self.repo.update_workflow_context(workflow_id, ctx)
            self.repo.update_workflow_fields(workflow_id, cron_expression=None)
            workflow = self.repo.get_workflow(workflow_id, user_id)
            assert workflow is not None
            return self._mutator_result(
                workflow, next_step="trigger is manual; call run_workflow to execute"
            )

        scheduled_at = ScheduleParser.parse(raw)
        is_cron = ScheduleParser.is_cron(raw)
        ctx = self._load_context(workflow)
        ctx["trigger"] = {
            "type": "cron" if is_cron else "manual",
            "cron": raw if is_cron else None,
            "tz": "UTC",
            "overlap_policy": "run_once_catchup",
        }
        self.repo.update_workflow_context(workflow_id, ctx)
        self.repo.update_workflow_fields(
            workflow_id,
            cron_expression=raw if is_cron else None,
            scheduled_at=scheduled_at,
            status="scheduled",
        )
        self.scheduler.register(workflow_id, scheduled_at, self._on_fire)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(
            workflow,
            next_step=f"trigger set to {raw!r}",
            extra={"trigger": ctx["trigger"]},
        )

    def set_workflow_source(
        self,
        user_id: str,
        workflow_id: str,
        connector_id: str,
        connector_env: str | None = None,
    ) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        connector = self.repo.get_connector(connector_id, user_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        if connector_env:
            env = self.repo.get_connector_env(connector_id, connector_env)
            if env is None:
                raise ValueError(f"Environment {connector_env!r} not found on connector")
        ctx = self._load_context(workflow)
        inp = dict(ctx.get("input") or {})
        inp["connector_id"] = connector_id
        if connector_env:
            inp["connector_env"] = connector_env
        ctx["input"] = inp
        self.repo.update_workflow_context(workflow_id, ctx)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(
            workflow,
            next_step="source bound; open ui_url",
            extra={
                "connector_id": connector_id,
                "connector_name": connector.name,
                "connector_env": connector_env
                or inp.get("connector_env")
                or "default",
            },
        )

    def set_workflow_step_connector(
        self,
        user_id: str,
        workflow_id: str,
        step: str,
        *,
        connector_id: str | None = None,
        env: str | None = None,
        config: dict | None = None,
        clear: bool = False,
    ) -> dict:
        """Set or clear graph.node_config[step] connector binding."""
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        ctx = self._load_context(workflow)
        graph = dict(ctx.get("graph") or {})
        nodes = list(graph.get("nodes") or [])
        if step not in nodes:
            raise ValueError(f"Step {step!r} is not in the workflow graph")
        node_config = dict(graph.get("node_config") or {})
        if clear:
            node_config.pop(step, None)
        else:
            entry = dict(node_config.get(step) or {})
            if connector_id is not None:
                if self.repo.get_connector(connector_id, user_id) is None:
                    raise ValueError(f"Connector not found: {connector_id}")
                entry["connector_id"] = connector_id
            if env is not None:
                entry["env"] = env
            if config is not None:
                entry["config"] = config
            node_config[step] = entry
        graph["node_config"] = node_config
        ctx["graph"] = graph
        self.repo.update_workflow_context(workflow_id, ctx)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(
            workflow,
            next_step="step connector binding updated",
            extra={"step": step, "node_config": node_config.get(step)},
        )

    def set_workflow_destination(
        self, user_id: str, workflow_id: str, destination_id: str
    ) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        destination = self.repo.get_destination(destination_id, user_id)
        if destination is None:
            raise ValueError(f"Destination not found: {destination_id}")
        ctx = self._load_context(workflow)
        inp = dict(ctx.get("input") or {})
        inp["destination_id"] = destination_id
        ctx["input"] = inp
        self.repo.update_workflow_context(workflow_id, ctx)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(
            workflow,
            next_step="destination bound; open ui_url",
            extra={"destination_id": destination_id, "destination_name": destination.name},
        )

    def add_workflow_step(
        self,
        user_id: str,
        workflow_id: str,
        *,
        step: str | None = None,
        hint: str | None = None,
    ) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        step_id = step or (resolve_step_hint(hint or "") if hint else None)
        if not step_id:
            raise ValueError(
                f"Could not resolve step from step={step!r} hint={hint!r}. "
                f"Known: {sorted(KNOWN_STEPS)}"
            )
        if step_id not in KNOWN_STEPS:
            raise ValueError(f"Unknown step {step_id!r}. Known: {sorted(KNOWN_STEPS)}")
        ctx = self._load_context(workflow)
        graph = dict(ctx.get("graph") or {})
        nodes = list(graph.get("nodes") or [])
        edges = [list(e) for e in (graph.get("edges") or [])]
        if step_id in nodes:
            return self._mutator_result(
                workflow, next_step=f"step {step_id} already present", extra={"needs_input": False}
            )
        wired = wire_step(nodes, step_id)
        if wired.get("needs_input") and not wired.get("edges"):
            return {
                **self._mutator_result(workflow, next_step=wired.get("message", "")),
                "needs_input": True,
                "candidates": wired.get("candidates") or [],
                "pending_step": step_id,
            }
        nodes.append(step_id)
        for e in wired.get("edges") or []:
            if e not in edges:
                edges.append(e)
        graph["nodes"] = nodes
        graph["edges"] = edges
        graph["entry"] = recompute_entry(nodes, edges)
        ctx["graph"] = graph
        ctx["action"] = "graph"
        self.repo.update_workflow_context(workflow_id, ctx)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        result = self._mutator_result(
            workflow, next_step="step added; open ui_url to see the DAG"
        )
        if wired.get("needs_input"):
            result["needs_input"] = True
            result["candidates"] = wired.get("candidates") or []
            result["message"] = wired.get("message")
        return result

    def remove_workflow_step(self, user_id: str, workflow_id: str, step: str) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        ctx = self._load_context(workflow)
        graph = dict(ctx.get("graph") or {})
        nodes = [n for n in (graph.get("nodes") or []) if n != step]
        edges = [list(e) for e in (graph.get("edges") or []) if step not in e]
        if not nodes:
            raise ValueError("Cannot remove the last step from a workflow")
        graph["nodes"] = nodes
        graph["edges"] = edges
        graph["entry"] = recompute_entry(nodes, edges)
        ctx["graph"] = graph
        self.repo.update_workflow_context(workflow_id, ctx)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(workflow, next_step=f"removed {step}; open ui_url")

    def connect_workflow_steps(
        self, user_id: str, workflow_id: str, source: str, target: str
    ) -> dict:
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        ctx = self._load_context(workflow)
        graph = dict(ctx.get("graph") or {})
        nodes = list(graph.get("nodes") or [])
        for n in (source, target):
            if n not in nodes:
                raise ValueError(f"Step {n!r} is not in the workflow graph")
        edges = [list(e) for e in (graph.get("edges") or [])]
        edge = [source, target]
        if edge not in edges:
            edges.append(edge)
        graph["edges"] = edges
        graph["entry"] = recompute_entry(nodes, edges)
        ctx["graph"] = graph
        self.repo.update_workflow_context(workflow_id, ctx)
        workflow = self.repo.get_workflow(workflow_id, user_id)
        assert workflow is not None
        return self._mutator_result(
            workflow, next_step=f"connected {source} → {target}", extra={"edge": edge}
        )

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
                    "duration_ms": r.duration_ms,
                    "output": json.loads(r.output) if r.output else None,
                    "error": r.error,
                    "steps": self.repo.serialize_run_steps(r.id),
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

        ctx = json.loads(workflow.context)
        destination_id = ctx.get("destination_id") or (ctx.get("input") or {}).get(
            "destination_id"
        )
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
        already at the destination; mode="overwrite" replaces them;
        mode="preview" samples into a temp DuckDB file and does not advance watermarks.
        """
        workflow = self.repo.get_workflow(workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        is_preview = mode == "preview"
        exec_mode = "append" if is_preview else mode
        preview_path = DATA_DIR / f"preview_{workflow_id}.duckdb" if is_preview else None

        run = self.repo.start_run(workflow_id)
        start_type = "run.preview.started" if is_preview else "run.started"
        live_url = live_workflow_url(workflow_id=workflow_id, run_id=run.id, page="runs")
        events.publish(
            f"run.{run.id}",
            start_type,
            {
                "workflow_id": workflow_id,
                "run_id": run.id,
                "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                "status": "running",
                "live_url": live_url,
            },
        )
        try:
            output = self._execute(
                workflow,
                self.repo,
                mode=exec_mode,
                preview=is_preview,
                preview_path=preview_path,
                run_id=run.id,
            )
            # Cooperative pause/cancel leaves status already set.
            run_row = self.repo.get_run(run.id)
            if run_row and run_row.status in ("paused", "cancelled"):
                return {
                    "run_id": run.id,
                    "workflow_id": workflow_id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": run_row.status,
                    "output": output,
                    "preview": is_preview,
                    "live_url": live_url,
                    "next_step": f"Open live_url: {live_url}",
                }
            self.repo.complete_run(run.id, output)
            run_done = self.repo.get_run(run.id)
            duration_ms = run_done.duration_ms if run_done else None
            if is_preview:
                events.publish(
                    f"run.{run.id}",
                    "run.preview.completed",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run.id,
                        "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                        "status": "completed",
                        "duration_ms": duration_ms,
                        "live_url": live_url,
                        "output": output,
                    },
                )
            else:
                self._advance_watermark(workflow_id, output)
                _publish_workflow_topics(
                    "run.succeeded",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run.id,
                        "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                        "status": "completed",
                        "duration_ms": duration_ms,
                        "live_url": live_url,
                        "output": output,
                    },
                    workflow,
                )
            return {
                "run_id": run.id,
                "workflow_id": workflow_id,
                "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                "status": "completed",
                "duration_ms": duration_ms,
                "steps": self.repo.serialize_run_steps(run.id),
                "output": output,
                "preview": is_preview,
                "live_url": live_url,
                "next_step": f"Open live_url to review the run: {live_url}",
            }
        except Exception as e:
            self.repo.fail_run(run.id, str(e))
            _publish_workflow_topics(
                    "run.failed",
                    {
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": "failed",
                    "live_url": live_url,
                    "error": str(e),
                },
                    workflow,
                )
            raise
        finally:
            if preview_path is not None and preview_path.exists():
                with suppress(OSError):
                    preview_path.unlink()

    def resume_paused_run(self, run_id: str, user_id: str) -> dict:
        """Continue a paused run (re-enters graph; idempotent steps safe for sync).

        ponytail: no LangGraph checkpoint mid-graph → re-run remaining from start.
        """
        run = self.repo.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        if run.status != "paused":
            raise ValueError(f"Run is not paused (status={run.status})")
        workflow = self.repo.get_workflow(run.workflow_id, user_id)
        if workflow is None:
            raise ValueError(f"Workflow not found: {run.workflow_id}")

        self.repo.mark_run_running(run_id)
        live_url = live_workflow_url(workflow_id=workflow.id, run_id=run_id)
        events.publish(
            f"run.{run_id}",
            "run.started",
            {
                "workflow_id": workflow.id,
                "run_id": run_id,
                "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                "status": "running",
                "live_url": live_url,
            },
        )
        try:
            output = self._execute(workflow, self.repo, mode="append", run_id=run_id)
            run_row = self.repo.get_run(run_id)
            if run_row and run_row.status in ("paused", "cancelled"):
                return {
                    "run_id": run_id,
                    "workflow_id": workflow.id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": run_row.status,
                    "output": output,
                    "live_url": live_url,
                    "next_step": f"Open live_url: {live_url}",
                }
            self.repo.complete_run(run_id, output)
            self._advance_watermark(workflow.id, output)
            run_done = self.repo.get_run(run_id)
            duration_ms = run_done.duration_ms if run_done else None
            _publish_workflow_topics(
                    "run.succeeded",
                    {
                    "workflow_id": workflow.id,
                    "run_id": run_id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": "completed",
                    "duration_ms": duration_ms,
                    "live_url": live_url,
                    "output": output,
                },
                    workflow,
                )
            return {
                "run_id": run_id,
                "workflow_id": workflow.id,
                "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                "status": "completed",
                "duration_ms": duration_ms,
                "steps": self.repo.serialize_run_steps(run_id),
                "output": output,
                "live_url": live_url,
                "next_step": f"Open live_url to review the run: {live_url}",
            }
        except Exception as e:
            self.repo.fail_run(run_id, str(e))
            _publish_workflow_topics(
                    "run.failed",
                    {
                    "workflow_id": workflow.id,
                    "run_id": run_id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": "failed",
                    "live_url": live_url,
                    "error": str(e),
                },
                    workflow,
                )
            raise

    def pause_run(self, run_id: str) -> dict:
        """Request soft pause after the current LangGraph step."""
        run = self.repo.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        if run.status not in ("running", "paused"):
            raise ValueError(f"Cannot pause run in status={run.status}")
        self.repo.set_run_control(run_id, "pause_requested")
        live_url = live_workflow_url(workflow_id=run.workflow_id, run_id=run_id)
        return {
            "run_id": run_id,
            "status": run.status,
            "control": "pause_requested",
            "live_url": live_url,
            "next_step": f"Pause takes effect after the current step. Open {live_url}",
        }

    def stop_run(self, run_id: str) -> dict:
        """Request cancel after the current LangGraph step."""
        run = self.repo.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        if run.status == "paused":
            # Already between steps — cancel immediately.
            self.repo.mark_run_cancelled(run_id)
            live_url = live_workflow_url(workflow_id=run.workflow_id, run_id=run_id)
            events.publish(
                f"run.{run_id}",
                "run.cancelled",
                {
                    "workflow_id": run.workflow_id,
                    "run_id": run_id,
                    "status": "cancelled",
                    "live_url": live_url,
                },
            )
            return {
                "run_id": run_id,
                "status": "cancelled",
                "live_url": live_url,
                "next_step": f"Open live_url: {live_url}",
            }
        if run.status != "running":
            raise ValueError(f"Cannot stop run in status={run.status}")
        self.repo.set_run_control(run_id, "cancel_requested")
        live_url = live_workflow_url(workflow_id=run.workflow_id, run_id=run_id)
        return {
            "run_id": run_id,
            "status": "running",
            "control": "cancel_requested",
            "live_url": live_url,
            "next_step": f"Stop takes effect after the current step. Open {live_url}",
        }

    def _execute(
        self,
        workflow: WorkflowModel,
        repo: WorkflowRepository,
        mode: str = "append",
        preview: bool = False,
        preview_path: Path | None = None,
        run_id: str | None = None,
    ) -> dict:
        """Produce this workflow's run output. Most workflows are generic
        (AI-agent tasks with no real side effect here); `graph` DAG
        workflows (langfuse export included) are the one action this
        backend actually executes, via LangGraph steps (steps.py).
        """
        context = json.loads(workflow.context)
        if context.get("action") == "graph":
            initial = self._resolve_graph_input(context.get("input", {}), repo, workflow.user_id)
            if preview:
                initial["limit"] = min(int(initial.get("limit", 50)), 5)
                if preview_path is not None and "dest_config" in initial:
                    initial["dest_config"] = {
                        **initial["dest_config"],
                        "db_path": str(preview_path),
                    }
            elif workflow.watermark_at is not None:
                initial["since"] = workflow.watermark_at.isoformat()
            # Soft-upgrade stored IR so existing langfuse syncs get report+email steps.
            graph = context.get("graph") or {}
            nodes = list(graph.get("nodes") or [])
            if (
                "refresh_retailer_mart" in nodes
                and "build_retailer_report" not in nodes
            ):
                graph = SOURCES["langfuse"]["graph"]
                nodes = list(graph.get("nodes") or [])
            step_creds = self._build_step_creds(
                nodes=nodes,
                input_=context.get("input") or {},
                node_config=graph.get("node_config") or {},
                repo=repo,
                user_id=workflow.user_id,
                base_resolved=initial,
            )
            compiled = build_graph(graph)
            state = {**initial, "workflow_id": workflow.id, "mode": mode}
            if step_creds:
                state["_step_creds"] = step_creds
            slug = _workflow_slug(workflow)
            if slug:
                state["slug"] = slug
                state["process_slug"] = slug
            if run_id:
                state["run_id"] = run_id
            if initial.get("preview_only"):
                state["preview_only"] = True
            steps_done: list[dict] = []
            # ponytail: stream updates fire after each node — duration ≈ gap since prior finish
            t_prev = time.perf_counter()
            for update in compiled.stream(state, stream_mode="updates"):
                for step_name, step_state in update.items():
                    t_now = time.perf_counter()
                    duration_ms = max(0, int(round((t_now - t_prev) * 1000)))
                    t_prev = t_now
                    # ponytail: updates stream fires after the node finishes — started
                    # is best-effort for UI sequencing; true mid-step running needs
                    # per-step publish inside handlers → astream_events.
                    step_payload = {
                        "step": step_name,
                        "workflow_id": workflow.id,
                        "run_id": run_id,
                        "status": "running",
                        "duration_ms": duration_ms,
                        "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    }
                    events.publish(
                        f"run.{run_id or workflow.id}",
                        "run.step.started",
                        step_payload,
                    )
                    state = step_state
                    step_row = {
                        "id": step_name,
                        "status": "succeeded",
                        "duration_ms": duration_ms,
                    }
                    steps_done.append(step_row)
                    if run_id:
                        repo.record_run_step(
                            run_id,
                            step_name,
                            status="succeeded",
                            duration_ms=duration_ms,
                        )
                    events.publish(
                        f"run.{run_id or workflow.id}",
                        "run.step",
                        {**step_payload, "status": "succeeded"},
                    )
                # Cooperative cancel/pause between steps (after recording the step).
                if run_id:
                    repo.db.expire_all()  # see pause/stop from other API sessions
                    run_row = repo.get_run(run_id)
                    ctrl = run_row.control if run_row else None
                    if ctrl == "cancel_requested":
                        state = {**state, "steps": steps_done}
                        repo.mark_run_cancelled(run_id, state)
                        events.publish(
                            f"run.{run_id}",
                            "run.cancelled",
                            {
                                "workflow_id": workflow.id,
                                "run_id": run_id,
                                "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                                "status": "cancelled",
                                "live_url": live_workflow_url(
                                    workflow_id=workflow.id, run_id=run_id
                                ),
                            },
                        )
                        return state
                    if ctrl == "pause_requested":
                        state = {**state, "steps": steps_done}
                        repo.mark_run_paused(run_id, state)
                        events.publish(
                            f"run.{run_id}",
                            "run.paused",
                            {
                                "workflow_id": workflow.id,
                                "run_id": run_id,
                                "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                                "status": "paused",
                                "live_url": live_workflow_url(
                                    workflow_id=workflow.id, run_id=run_id
                                ),
                            },
                        )
                        return state
            state = {**state, "steps": steps_done}
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
        # Replay IR uses connection_id; export IR uses connector_id — accept both.
        connector_id = resolved.pop("connector_id", None) or resolved.pop("connection_id", None)
        connector_env = resolved.pop("connector_env", None)
        if connector_id is not None:
            creds = repo.resolve_connector_credentials(
                connector_id, user_id, env_key=connector_env
            )
            resolved.update(
                host=creds["host"],
                public_key=creds["public_key"],
                secret_key=creds["secret_key"],
            )
            resolved["_default_connector_id"] = connector_id
            resolved["_default_connector_env"] = creds.get("env_key")

        destination_id = resolved.pop("destination_id", None)
        if destination_id is not None:
            destination = repo.get_destination(destination_id, user_id)
            if destination is None:
                raise ValueError(f"Destination not found: {destination_id}")
            resolved.update(dest_type=destination.type, dest_config=json.loads(destination.config))

        return resolved

    def _build_step_creds(
        self,
        *,
        nodes: list[str],
        input_: dict,
        node_config: dict,
        repo: WorkflowRepository,
        user_id: str,
        base_resolved: dict,
    ) -> dict[str, dict]:
        """Pre-resolve per-step connector credentials for graph._merging."""
        default_id = input_.get("connector_id") or input_.get("connection_id")
        default_env = input_.get("connector_env")
        step_creds: dict[str, dict] = {}
        for step in nodes:
            nc = (node_config or {}).get(step) or {}
            cid = nc.get("connector_id") or default_id
            env = nc.get("env") or default_env
            cfg = dict(nc.get("config") or {})
            if not cid:
                if cfg:
                    step_creds[step] = cfg
                continue
            creds = repo.resolve_connector_credentials(cid, user_id, env_key=env)
            step_creds[step] = {
                "host": creds["host"],
                "public_key": creds["public_key"],
                "secret_key": creds["secret_key"],
                **cfg,
            }
        # Ensure base keys exist for steps without overrides
        if not step_creds and (
            base_resolved.get("host") or base_resolved.get("public_key")
        ):
            return {}
        return step_creds

    def _advance_watermark(
        self,
        workflow_id: str,
        output: dict,
        repo: WorkflowRepository | None = None,
    ) -> None:
        """Advance watermark_at from last_timestamp after a successful production run."""
        last_ts_str = output.get("last_timestamp") if isinstance(output, dict) else None
        if not last_ts_str:
            return
        last_ts = (
            last_ts_str
            if isinstance(last_ts_str, datetime)
            else datetime.fromisoformat(str(last_ts_str).replace("Z", "+00:00"))
        )
        target = repo or self.repo
        target.update_workflow_watermark(workflow_id, last_ts)

    def _on_fire(self, workflow_id: str) -> None:
        """Called by APScheduler when a workflow's scheduled time arrives."""
        db = SessionLocal()
        repo = WorkflowRepository(db)
        run = repo.start_run(workflow_id)
        try:
            workflow = repo.get_workflow(workflow_id, user_id=None)
            if workflow is None:
                raise ValueError(f"Workflow not found: {workflow_id}")
            live_url = live_workflow_url(workflow_id=workflow_id, run_id=run.id)
            events.publish(
                f"run.{run.id}",
                "run.started",
                {
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": "running",
                    "live_url": live_url,
                },
            )
            output = self._execute(workflow, repo, run_id=run.id)
            repo.complete_run(run.id, output)
            self._advance_watermark(workflow_id, output, repo=repo)
            _publish_workflow_topics(
                    "run.succeeded",
                    {
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "slug": _workflow_slug(workflow), "process_slug": _workflow_slug(workflow),
                    "status": "completed",
                    "live_url": live_url,
                    "output": output,
                },
                    workflow,
                )

            if workflow.cron_expression and ScheduleParser.is_cron(workflow.cron_expression):
                next_run = ScheduleParser.parse(workflow.cron_expression)
                repo.reschedule_workflow(workflow_id, next_run)
                self.scheduler.register(workflow_id, next_run, self._on_fire)
                _publish_workflow_topics(
                    "workflow.scheduled",
                    {"workflow_id": workflow_id, "status": "scheduled"},
                    workflow,
                )
            else:
                repo.update_workflow_status(workflow_id, "completed")
                _publish_workflow_topics(
                    "workflow.completed",
                    {"workflow_id": workflow_id, "status": "completed"},
                    workflow,
                )
        except Exception as e:
            repo.fail_run(run.id, str(e))
            repo.update_workflow_status(workflow_id, "failed")
            workflow = repo.get_workflow(workflow_id, user_id=None)
            fail_payload = {
                "workflow_id": workflow_id,
                "run_id": run.id,
                "error": str(e),
                "status": "failed",
                "slug": _workflow_slug(workflow) if workflow else None,
                "process_slug": _workflow_slug(workflow) if workflow else None,
                "live_url": live_workflow_url(workflow_id=workflow_id, run_id=run.id),
            }
            if workflow:
                _publish_workflow_topics("run.failed", fail_payload, workflow)
            else:
                events.publish(f"run.{run.id}", "run.failed", fail_payload)
        finally:
            db.close()
