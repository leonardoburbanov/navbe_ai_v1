"""FastAPI application: REST API, SSE, and FastMCP mount."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import duckdb
import navbe_core.steps  # noqa: F401 — registers @step handlers
import navbe_mcp.tools  # noqa: F401 — registers MCP tool handlers
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans
from navbe_connectors.langfuse import fetch_recent_traces, test_langfuse_connection
from navbe_core.agent import WorkflowAgent
from navbe_core.config import DATA_DIR, NAVBE_HOME
from navbe_core.models import (
    ConnectorModel,
    ConnectorSyncModel,
    DestinationModel,
    SessionLocal,
    UserModel,
    get_db,
    init_db,
)
from navbe_core.repository import WorkflowRepository
from navbe_destinations.duckdb import DESTINATION_TYPES, list_replay_results
from navbe_mcp.registry import dispatch
from navbe_mcp.tools.list_analysis_templates import RETAILER_TEMPLATE
from navbe_notify import bus as events
from navbe_scheduler.scheduler import APSchedulerAdapter
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from navbe_api.auth import get_current_user
from navbe_api.graph import workflow_to_flow_graph
from navbe_api.sse import stream_all_events, stream_workflow_events

DEMO_USER_ID = "demo"
DEMO_USER_EMAIL = "demo@navbe.local"


class QueryWorkflowRequest(BaseModel):
    """Body for Control UI destination queries."""

    sql: str
    page: int = 1
    page_size: int = 10


scheduler_adapter = APSchedulerAdapter()


def ensure_demo_user(db: Session) -> UserModel:
    """Ensure the local demo user exists (single-profile hub)."""
    user = db.query(UserModel).filter(UserModel.id == DEMO_USER_ID).first()
    if user is None:
        user = UserModel(id=DEMO_USER_ID, email=DEMO_USER_EMAIL)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _run_tool(tool_name: str, **kwargs) -> dict:
    """Dispatch an MCP tool against a fresh DB session as the demo user."""
    db = SessionLocal()
    try:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        return dispatch(tool_name, agent=agent, user_id=DEMO_USER_ID, **kwargs)
    finally:
        db.close()


# -- MCP server -------------------------------------------------------------

mcp = FastMCP("Navbe")


@mcp.tool
def suggest_workflow(hint: str) -> dict:
    """Propose a DAG workflow for a data source named in free text."""
    try:
        return _run_tool("suggest_workflow", hint=hint)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool
def schedule_workflow(
    name: str, task: str, when: str, context: dict = {}, agent_id: str | None = None
) -> dict:
    """Schedule a workflow. `when`: '+30s', '+1h', 'monday 9am', or cron."""
    return _run_tool(
        "schedule_workflow", name=name, task=task, when=when, context=context, agent_id=agent_id
    )


@mcp.tool
def recall_workflow(workflow_id: str) -> dict:
    """Recall a workflow's details, context, and last run result."""
    try:
        return _run_tool("recall_workflow", workflow_id=workflow_id)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool
def list_workflows() -> dict:
    """List all workflows with status and schedule."""
    return _run_tool("list_workflows")


@mcp.tool
def run_workflow(workflow_id: str, mode: str = "append") -> dict:
    """Run a workflow immediately. mode='append' or 'overwrite'."""
    try:
        return _run_tool("run_workflow", workflow_id=workflow_id, mode=mode)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool
def create_connector(name: str, host: str, public_key: str, secret_key: str) -> dict:
    """Register a Langfuse connector with host and API keys."""
    return _run_tool(
        "create_connector", name=name, host=host, public_key=public_key, secret_key=secret_key
    )


@mcp.tool
def list_connectors() -> dict:
    """List all configured Langfuse connectors."""
    return _run_tool("list_connectors")


@mcp.tool
def query_langfuse(
    connector_id: str, page: int = 1, page_size: int = 10, include_observations: bool = False
) -> dict:
    """Fetch one page of traces directly from Langfuse."""
    return _run_tool(
        "query_langfuse",
        connector_id=connector_id,
        page=page,
        page_size=page_size,
        include_observations=include_observations,
    )


@mcp.tool
def create_destination(type: str, name: str, config: dict = {}) -> dict:
    """Register a destination. type: 'csv_file' or 'duckdb'."""
    return _run_tool("create_destination", type=type, name=name, config=config)


@mcp.tool
def list_destinations() -> dict:
    """List all configured destinations."""
    return _run_tool("list_destinations")


@mcp.tool
def create_langfuse_export_workflow(
    name: str,
    connector_id: str,
    destination_id: str,
    when: str = "+5s",
    include_observations: bool = False,
) -> dict:
    """Schedule a Langfuse → destination export workflow."""
    try:
        return _run_tool(
            "create_langfuse_export_workflow",
            name=name,
            connector_id=connector_id,
            destination_id=destination_id,
            when=when,
            include_observations=include_observations,
        )
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool
def describe_destination(destination_id: str) -> dict:
    """Show column names/types on a destination (table `traces`)."""
    return _run_tool("describe_destination", destination_id=destination_id)


@mcp.tool
def query_destination(destination_id: str, sql: str, page: int = 1, page_size: int = 10) -> dict:
    """Run a read-only SELECT against a destination's `traces` table."""
    return _run_tool(
        "query_destination",
        destination_id=destination_id,
        sql=sql,
        page=page,
        page_size=page_size,
    )


@mcp.tool
def query_workflow_destination(
    workflow_id: str, sql: str, page: int = 1, page_size: int = 10
) -> dict:
    """Run a read-only SELECT against a workflow's destination."""
    return _run_tool(
        "query_workflow_destination",
        workflow_id=workflow_id,
        sql=sql,
        page=page,
        page_size=page_size,
    )


@mcp.tool
def subscribe(subscriber_id: str, topics: list[str] | None = None) -> dict:
    """Register as a named event-bus subscriber; then poll with pull_events."""
    return _run_tool("subscribe", subscriber_id=subscriber_id, topics=topics)


@mcp.tool
def pull_events(subscriber_id: str, limit: int = 50) -> dict:
    """Poll events since this subscriber's cursor and advance it."""
    return _run_tool("pull_events", subscriber_id=subscriber_id, limit=limit)


@mcp.tool
def get_process_status(process_slug: str) -> dict:
    """Shared live status for a named process (any agent)."""
    return _run_tool("get_process_status", process_slug=process_slug)


@mcp.tool
def list_processes() -> dict:
    """List named processes visible to all agents on this hub."""
    return _run_tool("list_processes")


@mcp.tool
def list_analysis_templates(destination_id: str) -> dict:
    """List analysis templates affordable for a destination."""
    return _run_tool("list_analysis_templates", destination_id=destination_id)


@mcp.tool
def replay_trace_to_api(
    trace_id: str,
    connection_id: str,
    api_url: str,
    auth: dict,
    method: str = "POST",
    input_mapping: dict | None = None,
    destination_id: str | None = None,
    save_as_workflow: bool = False,
) -> dict:
    """Replay a Langfuse trace against an API and return a structured diff."""
    try:
        return _run_tool(
            "replay_trace_to_api",
            trace_id=trace_id,
            connection_id=connection_id,
            api_url=api_url,
            auth=auth,
            method=method,
            input_mapping=input_mapping,
            destination_id=destination_id,
            save_as_workflow=save_as_workflow,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def preview_workflow(workflow_id: str) -> dict:
    """Dry-run a workflow into a preview sandbox; does not advance watermarks."""
    try:
        return _run_tool("preview_workflow", workflow_id=workflow_id)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool
def configure_resend(
    api_key: str,
    from_addr: str = "onboarding@resend.dev",
) -> dict:
    """Configure Resend API for daily HTML email reports (key encrypted at rest)."""
    return _run_tool("configure_resend", api_key=api_key, from_addr=from_addr)


@mcp.tool
def configure_email(
    host: str,
    username: str,
    password: str,
    from_addr: str,
    port: int = 587,
    use_tls: bool = True,
) -> dict:
    """Configure SMTP for daily HTML email reports (fallback; prefer configure_resend)."""
    return _run_tool(
        "configure_email",
        host=host,
        username=username,
        password=password,
        from_addr=from_addr,
        port=port,
        use_tls=use_tls,
    )


@mcp.tool
def preview_daily_report(destination_id: str) -> dict:
    """Build retailer HTML report to ~/.navbe/reports/ without sending email."""
    try:
        return _run_tool("preview_daily_report", destination_id=destination_id)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def schedule_daily_report(
    destination_id: str,
    email_to: str,
    when: str = "0 23 * * *",
    name: str = "langfuse_daily_report",
) -> dict:
    """Schedule end-of-day langfuse_daily_report HTML email (default 23:00 UTC)."""
    return _run_tool(
        "schedule_daily_report",
        destination_id=destination_id,
        email_to=email_to,
        when=when,
        name=name,
    )


@mcp.tool
def send_daily_report(
    workflow_id: str | None = None,
    destination_id: str | None = None,
    email_to: str | None = None,
) -> dict:
    """Send the daily retailer HTML email now."""
    try:
        return _run_tool(
            "send_daily_report",
            workflow_id=workflow_id,
            destination_id=destination_id,
            email_to=email_to,
        )
    except Exception as e:
        return {"error": str(e)}


mcp_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    events.init(NAVBE_HOME / "events.db")
    init_db()
    db = SessionLocal()
    try:
        ensure_demo_user(db)
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        scheduler_adapter.start()
        scheduler_adapter.load_existing(repo.get_scheduled_workflows(), agent._on_fire)
    finally:
        db.close()
    events.bind_loop(asyncio.get_running_loop())
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app with MCP mounted at /mcp and CORS for the Control UI."""
    app = FastAPI(
        title="Navbe",
        lifespan=combine_lifespans(_lifespan, mcp_app.lifespan),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/mcp", mcp_app)
    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    """Attach REST and SSE routes to the app."""

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/")
    def root() -> dict:
        return {
            "name": "Navbe",
            "description": "Local hub for AI agent workflow orchestration via MCP.",
            "mcp_endpoint": "/mcp/",
            "health": "/health",
            "events_sse": "/events/sse",
        }

    class CreateUserRequest(BaseModel):
        email: str

    @app.post("/api/users", status_code=201)
    def create_user(payload: CreateUserRequest, db: Session = Depends(get_db)) -> dict:
        repo = WorkflowRepository(db)
        if db.query(UserModel).filter(UserModel.email == payload.email).first():
            raise HTTPException(status_code=409, detail="User already exists")
        user = repo.create_user(payload.email)
        return {"user_id": user.id, "email": user.email, "api_key": user.api_key}

    @app.get("/api/workflows")
    def api_list_workflows(
        user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> dict:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        return dispatch("list_workflows", agent=agent, user_id=user.id)

    @app.get("/api/workflows/{workflow_id}")
    def api_get_workflow(
        workflow_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "recall_workflow", agent=agent, user_id=user.id, workflow_id=workflow_id
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/api/workflows/{workflow_id}/stream")
    def api_stream_workflow(
        workflow_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        repo = WorkflowRepository(db)
        if repo.get_workflow(workflow_id, user.id) is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return stream_workflow_events(workflow_id)

    @app.get("/events/sse")
    def api_events_sse():
        """Hub-wide SSE stream for the Control UI (Sprint 0: no auth)."""
        return stream_all_events()

    # -- Control UI (local hub, demo user, no API key) ---------------------

    @app.get("/api/processes")
    def api_list_processes(db: Session = Depends(get_db)) -> dict:
        """Named processes with last run / next run / watermark for the cockpit."""
        repo = WorkflowRepository(db)
        processes = []
        for w in repo.list_workflows_with_slug(DEMO_USER_ID):
            last = repo.get_last_run(w.id)
            processes.append(
                {
                    "process_slug": w.process_slug,
                    "workflow_id": w.id,
                    "name": w.name,
                    "status": w.status,
                    "scheduled_at": w.scheduled_at.isoformat() if w.scheduled_at else None,
                    "watermark": w.watermark_at.isoformat() if w.watermark_at else None,
                    "last_run": (
                        {
                            "run_id": last.id,
                            "status": last.status,
                            "started_at": last.started_at.isoformat(),
                            "completed_at": (
                                last.completed_at.isoformat() if last.completed_at else None
                            ),
                        }
                        if last
                        else None
                    ),
                }
            )
        return {"processes": processes}

    @app.get("/api/runs/{workflow_id}")
    def api_runs(
        workflow_id: str,
        page: int = 1,
        page_size: int = 20,
        db: Session = Depends(get_db),
    ) -> dict:
        """Paginated run history for one workflow (Control UI)."""
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "list_workflow_runs",
                agent=agent,
                user_id=DEMO_USER_ID,
                workflow_id=workflow_id,
                page=page,
                page_size=page_size,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/api/catalog")
    def api_catalog(db: Session = Depends(get_db)) -> dict:
        """Connectors, destinations, and analysis templates for the catalog page."""
        repo = WorkflowRepository(db)
        connectors = [
            {
                "id": c.id,
                "type": c.type,
                "name": c.name,
                "host": c.host,
                "status": c.status,
            }
            for c in repo.list_connectors(DEMO_USER_ID)
        ]
        destinations = []
        for d in repo.list_destinations(DEMO_USER_ID):
            templates = [dict(RETAILER_TEMPLATE)] if d.type == "duckdb" else []
            try:
                cfg = json.loads(d.config) if d.config else {}
            except json.JSONDecodeError:
                cfg = {}
            destinations.append(
                {
                    "id": d.id,
                    "type": d.type,
                    "name": d.name,
                    "schema_version": 1 if d.type == "duckdb" else None,
                    "config_summary": {
                        "db_path": cfg.get("db_path"),
                        "table": cfg.get("table"),
                    },
                    "templates": templates,
                }
            )
        return {
            "connectors": connectors,
            "destinations": destinations,
            "connector_types": ["langfuse"],
            "destination_types": sorted(DESTINATION_TYPES),
        }

    class ResendSettingsRequest(BaseModel):
        api_key: str
        from_addr: str = "onboarding@resend.dev"

    class ReportDestinationRequest(BaseModel):
        destination_id: str

    class ScheduleReportRequest(BaseModel):
        destination_id: str
        email_to: str
        when: str = "0 23 * * *"
        name: str = "langfuse_daily_report"

    class SendReportRequest(BaseModel):
        workflow_id: str | None = None
        destination_id: str | None = None
        email_to: str | None = None

    @app.get("/api/settings/email")
    def api_email_status() -> dict:
        """Redacted email/Resend status for the Control UI Settings page."""
        from navbe_notify.email_report import email_status_redacted

        return email_status_redacted()

    @app.post("/api/settings/resend")
    def api_configure_resend(payload: ResendSettingsRequest, db: Session = Depends(get_db)) -> dict:
        """Save Resend API key (encrypted) via the same MCP tool path."""
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        return dispatch(
            "configure_resend",
            agent=agent,
            user_id=DEMO_USER_ID,
            api_key=payload.api_key,
            from_addr=payload.from_addr,
        )

    @app.post("/api/reports/preview")
    def api_preview_report(payload: ReportDestinationRequest, db: Session = Depends(get_db)) -> dict:
        """Build retailer HTML report without sending email."""
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "preview_daily_report",
                agent=agent,
                user_id=DEMO_USER_ID,
                destination_id=payload.destination_id,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.post("/api/reports/schedule")
    def api_schedule_report(payload: ScheduleReportRequest, db: Session = Depends(get_db)) -> dict:
        """Schedule langfuse_daily_report cron email."""
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        return dispatch(
            "schedule_daily_report",
            agent=agent,
            user_id=DEMO_USER_ID,
            destination_id=payload.destination_id,
            email_to=payload.email_to,
            when=payload.when,
            name=payload.name,
        )

    @app.post("/api/reports/send")
    def api_send_report(payload: SendReportRequest, db: Session = Depends(get_db)) -> dict:
        """Send the daily retailer HTML email now."""
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "send_daily_report",
                agent=agent,
                user_id=DEMO_USER_ID,
                workflow_id=payload.workflow_id,
                destination_id=payload.destination_id,
                email_to=payload.email_to,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/api/workflows/{workflow_id}/graph")
    def api_workflow_graph(workflow_id: str, db: Session = Depends(get_db)) -> dict:
        """Workflow IR shaped for React Flow (positions filled by dagre on the client)."""
        repo = WorkflowRepository(db)
        workflow = repo.get_workflow(workflow_id, DEMO_USER_ID)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow_to_flow_graph(workflow.context)

    @app.get("/api/replays")
    def api_replays(
        workflow_id: str | None = None,
        destination_id: str | None = None,
        db: Session = Depends(get_db),
    ) -> dict:
        """List replay_results from DuckDB destinations (Control UI)."""
        repo = WorkflowRepository(db)
        dest_ids: list[str] = []

        if destination_id:
            dest_ids = [destination_id]
        elif workflow_id:
            workflow = repo.get_workflow(workflow_id, DEMO_USER_ID)
            if workflow is None:
                raise HTTPException(status_code=404, detail="Workflow not found")
            ctx = json.loads(workflow.context)
            did = (ctx.get("input") or {}).get("destination_id")
            if did:
                dest_ids = [did]
        else:
            dest_ids = [d.id for d in repo.list_destinations(DEMO_USER_ID) if d.type == "duckdb"]

        rows: list[dict] = []
        for did in dest_ids:
            dest = repo.get_destination(did, DEMO_USER_ID)
            if dest is None or dest.type != "duckdb":
                continue
            config = json.loads(dest.config)
            db_path = config.get("db_path")
            if not db_path:
                continue
            try:
                for row in list_replay_results(db_path):
                    rows.append({**row, "destination_id": did})
            except Exception:
                continue

        rows.sort(key=lambda r: r.get("ts") or "", reverse=True)
        return {"replays": rows}

    @app.post("/api/workflows/{workflow_id}/query")
    def api_query_workflow_destination(
        workflow_id: str,
        payload: QueryWorkflowRequest,
        db: Session = Depends(get_db),
    ) -> dict:
        """Run a read-only SELECT against a workflow destination (Control UI)."""
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "query_workflow_destination",
                agent=agent,
                user_id=DEMO_USER_ID,
                workflow_id=workflow_id,
                sql=payload.sql,
                page=payload.page,
                page_size=payload.page_size,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/api/workflows/{workflow_id}/runs")
    def api_list_workflow_runs(
        workflow_id: str,
        page: int = 1,
        page_size: int = 20,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "list_workflow_runs",
                agent=agent,
                user_id=user.id,
                workflow_id=workflow_id,
                page=page,
                page_size=page_size,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    class RunWorkflowRequest(BaseModel):
        mode: str = "append"

    @app.post("/api/workflows/{workflow_id}/run")
    def api_run_workflow(
        workflow_id: str,
        payload: RunWorkflowRequest = RunWorkflowRequest(),
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            return dispatch(
                "run_workflow",
                agent=agent,
                user_id=user.id,
                workflow_id=workflow_id,
                mode=payload.mode,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    class CreateLangfuseExportWorkflowRequest(BaseModel):
        name: str
        connector_id: str
        destination_id: str
        when: str = "+5s"
        include_observations: bool = False

    @app.post("/api/workflows/langfuse-export", status_code=201)
    def create_langfuse_export_workflow_api(
        payload: CreateLangfuseExportWorkflowRequest,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        try:
            workflow = agent.create_langfuse_export_workflow(
                user_id=user.id,
                name=payload.name,
                connector_id=payload.connector_id,
                destination_id=payload.destination_id,
                when=payload.when,
                include_observations=payload.include_observations,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {
            "workflow_id": workflow.id,
            "name": workflow.name,
            "scheduled_at": workflow.scheduled_at.isoformat(),
        }

    @app.get("/api/workflows/{workflow_id}/export")
    def download_workflow_export(
        workflow_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> FileResponse:
        repo = WorkflowRepository(db)
        workflow = repo.get_workflow(workflow_id, user.id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        last_run = repo.get_last_run(workflow_id)
        if last_run is None or last_run.status != "completed" or not last_run.output:
            raise HTTPException(status_code=409, detail="Export not ready yet")

        output = json.loads(last_run.output)
        output_path = output.get("output_path")
        if not output_path or not os.path.exists(output_path):
            raise HTTPException(status_code=404, detail="Export file not found")

        if output_path.endswith(".duckdb"):
            table = output.get("table") or "traces"
            csv_path = os.path.join(str(DATA_DIR), f"{workflow_id}.csv")
            con = duckdb.connect(output_path, read_only=True)
            try:
                con.execute(f"COPY \"{table}\" TO ? (HEADER, DELIMITER ',')", [csv_path])
            finally:
                con.close()
            output_path = csv_path

        return FileResponse(output_path, filename=f"{workflow_id}.csv", media_type="text/csv")

    class CreateConnectorRequest(BaseModel):
        name: str
        host: str
        public_key: str
        secret_key: str

    def _serialize_connector(connector: ConnectorModel) -> dict:
        return {
            "id": connector.id,
            "type": connector.type,
            "name": connector.name,
            "host": connector.host,
            "public_key": connector.public_key,
            "status": connector.status,
            "created_at": connector.created_at.isoformat(),
        }

    @app.post("/api/connectors", status_code=201)
    def create_connector_api(
        payload: CreateConnectorRequest,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        connector = repo.create_connector(
            user_id=user.id,
            name=payload.name,
            host=payload.host,
            public_key=payload.public_key,
            secret_key=payload.secret_key,
        )
        return _serialize_connector(connector)

    @app.get("/api/connectors")
    def list_connectors_api(
        user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> dict:
        repo = WorkflowRepository(db)
        return {"connectors": [_serialize_connector(c) for c in repo.list_connectors(user.id)]}

    @app.post("/api/connectors/{connector_id}/test")
    def test_connector(
        connector_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        connector = repo.get_connector(connector_id, user.id)
        if connector is None:
            raise HTTPException(status_code=404, detail="Connector not found")
        status = test_langfuse_connection(
            connector.host, connector.public_key, connector.secret_key
        )
        repo.update_connector_status(connector_id, status)
        connector.status = status
        return _serialize_connector(connector)

    @app.delete("/api/connectors/{connector_id}", status_code=204)
    def delete_connector(
        connector_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> None:
        repo = WorkflowRepository(db)
        if not repo.delete_connector(connector_id, user.id):
            raise HTTPException(status_code=404, detail="Connector not found")

    @app.get("/api/connectors/{connector_id}/traces")
    def api_query_langfuse(
        connector_id: str,
        page: int = 1,
        page_size: int = 10,
        include_observations: bool = False,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        agent = WorkflowAgent(repo, scheduler_adapter)
        return dispatch(
            "query_langfuse",
            agent=agent,
            user_id=user.id,
            connector_id=connector_id,
            page=page,
            page_size=page_size,
            include_observations=include_observations,
        )

    def _serialize_connector_sync(sync: ConnectorSyncModel) -> dict:
        return {
            "id": sync.id,
            "connector_id": sync.connector_id,
            "status": sync.status,
            "trace_count": sync.trace_count,
            "traces": json.loads(sync.output) if sync.output else None,
            "error": sync.error,
            "started_at": sync.started_at.isoformat(),
            "completed_at": sync.completed_at.isoformat() if sync.completed_at else None,
        }

    @app.post("/api/connectors/{connector_id}/sync")
    def sync_connector(
        connector_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        connector = repo.get_connector(connector_id, user.id)
        if connector is None:
            raise HTTPException(status_code=404, detail="Connector not found")
        sync = repo.start_connector_sync(connector_id)
        try:
            traces = fetch_recent_traces(connector.host, connector.public_key, connector.secret_key)
            repo.complete_connector_sync(sync.id, traces)
            repo.update_connector_status(connector_id, "connected")
        except Exception as e:
            repo.fail_connector_sync(sync.id, str(e))
            repo.update_connector_status(connector_id, "error")
        db.refresh(sync)
        return _serialize_connector_sync(sync)

    @app.get("/api/connectors/{connector_id}/syncs")
    def list_connector_syncs(
        connector_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        repo = WorkflowRepository(db)
        if repo.get_connector(connector_id, user.id) is None:
            raise HTTPException(status_code=404, detail="Connector not found")
        return {
            "syncs": [_serialize_connector_sync(s) for s in repo.list_connector_syncs(connector_id)]
        }

    class CreateDestinationRequest(BaseModel):
        type: str
        name: str
        config: dict = Field(default_factory=dict)

    def _serialize_destination(destination: DestinationModel) -> dict:
        return {
            "id": destination.id,
            "type": destination.type,
            "name": destination.name,
            "config": json.loads(destination.config),
            "created_at": destination.created_at.isoformat(),
        }

    @app.post("/api/destinations", status_code=201)
    def create_destination_api(
        payload: CreateDestinationRequest,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        if payload.type not in DESTINATION_TYPES:
            raise HTTPException(
                status_code=422, detail=f"Unsupported destination type: {payload.type}"
            )
        repo = WorkflowRepository(db)
        destination = repo.create_destination(
            user_id=user.id, type=payload.type, name=payload.name, config=payload.config
        )
        return _serialize_destination(destination)

    @app.get("/api/destinations")
    def list_destinations_api(
        user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> dict:
        repo = WorkflowRepository(db)
        return {
            "destinations": [_serialize_destination(d) for d in repo.list_destinations(user.id)]
        }

    @app.delete("/api/destinations/{destination_id}", status_code=204)
    def delete_destination(
        destination_id: str,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> None:
        repo = WorkflowRepository(db)
        if not repo.delete_destination(destination_id, user.id):
            raise HTTPException(status_code=404, detail="Destination not found")
