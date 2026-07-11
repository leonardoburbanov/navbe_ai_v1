"""MCP tools for daily HTML email retailer report (Sprint 5 / MVP C)."""

from __future__ import annotations

import json
import os

import duckdb
from navbe_core.agent import WorkflowAgent
from navbe_core.config import DATA_DIR
from navbe_core.models_report import ResendConfig, SmtpConfig
from navbe_notify import bus as events
from navbe_notify.email_report import (
    email_configured,
    probe_resend,
    probe_smtp,
    render_retailer_daily_html,
    save_report_preview,
    save_resend_config,
    save_smtp_config,
)
from navbe_transforms.retailer_report import build_retailer_report_payload
from pydantic import BaseModel

from navbe_mcp.registry import register


class ConfigureEmailResult(BaseModel):
    """Result of configure_email."""

    status: str
    probe: str
    next_step: str = "preview_daily_report"


def _configure_resend(
    agent: WorkflowAgent,
    user_id: str,
    api_key: str,
    from_addr: str = "onboarding@resend.dev",
) -> dict:
    """Store Resend API key (encrypted) for HTML email reports."""
    _ = agent, user_id
    if not api_key:
        return {
            "needs_input": {"fields": ["api_key", "from_addr"]},
            "next_step": "configure_resend with api_key",
        }
    cfg = ResendConfig(api_key=api_key, from_addr=from_addr or "onboarding@resend.dev")
    probe = probe_resend(cfg)
    if probe != "ok":
        return {"status": "rejected", "probe": probe, "next_step": "fix api_key / from_addr"}
    save_resend_config(cfg)
    return {
        "status": "saved",
        "provider": "resend",
        "from_addr": cfg.from_addr,
        "probe": probe,
        "next_step": "preview_daily_report then send_daily_report",
    }


def _configure_email(
    agent: WorkflowAgent,
    user_id: str,
    host: str,
    username: str,
    password: str,
    from_addr: str,
    port: int = 587,
    use_tls: bool = True,
) -> dict:
    """Store SMTP settings (password encrypted) and optionally probe login."""
    _ = agent, user_id
    if not host or not from_addr:
        return {
            "needs_input": {
                "fields": ["host", "port", "username", "password", "from_addr", "use_tls"],
            },
            "next_step": "configure_email with SMTP fields (or prefer configure_resend)",
        }
    cfg = SmtpConfig(
        host=host,
        port=port,
        username=username or "",
        password=password or "",
        from_addr=from_addr,
        use_tls=use_tls,
    )
    save_smtp_config(cfg)
    probe = probe_smtp(cfg)
    return ConfigureEmailResult(
        status="saved",
        probe=probe,
        next_step="preview_daily_report" if probe == "ok" else "fix SMTP credentials",
    ).model_dump()


def _resolve_db_path(agent: WorkflowAgent, user_id: str, destination_id: str) -> str:
    dest = agent.repo.get_destination(destination_id, user_id)
    if dest is None:
        raise ValueError(f"Destination not found: {destination_id}")
    config = json.loads(dest.config)
    return config.get("db_path") or os.path.join(str(DATA_DIR), "langfuse.duckdb")


def _preview_daily_report(
    agent: WorkflowAgent,
    user_id: str,
    destination_id: str,
) -> dict:
    """Build HTML report and save under ~/.navbe/reports/ without sending."""
    try:
        db_path = _resolve_db_path(agent, user_id, destination_id)
    except ValueError as e:
        return {"error": str(e), "next_step": "create_destination or list_destinations"}

    con = duckdb.connect(db_path, read_only=True)
    try:
        payload = build_retailer_report_payload(con)
    finally:
        con.close()

    html = render_retailer_daily_html(payload)
    path = save_report_preview(html, payload.report_date)
    events.publish(
        "process.langfuse_daily_report",
        "report.previewed",
        {
            "report_date": payload.report_date,
            "path": str(path),
            "totals": payload.totals,
            "destination_id": destination_id,
        },
    )
    return {
        "report_date": payload.report_date,
        "preview_path": str(path),
        "totals": payload.totals,
        "retailer_count": len(payload.rows),
        "next_step": "schedule_daily_report or send_daily_report",
    }


def _schedule_daily_report(
    agent: WorkflowAgent,
    user_id: str,
    destination_id: str,
    email_to: str,
    when: str = "0 23 * * *",
    name: str = "langfuse_daily_report",
) -> dict:
    """Schedule the end-of-day retailer email report workflow."""
    if not email_to:
        return {
            "needs_input": {"fields": ["email_to"]},
            "next_step": "schedule_daily_report with email_to",
        }
    if not email_configured():
        return {
            "needs_input": {
                "fields": ["api_key", "from_addr"],
            },
            "next_step": "configure_resend first",
        }
    try:
        workflow = agent.create_daily_report_workflow(
            user_id=user_id,
            destination_id=destination_id,
            email_to=email_to,
            when=when,
            name=name,
        )
    except ValueError as e:
        return {"error": str(e)}
    return {
        "workflow_id": workflow.id,
        "name": workflow.name,
        "process_slug": workflow.process_slug,
        "scheduled_at": workflow.scheduled_at.isoformat() if workflow.scheduled_at else None,
        "message": (
            f"Scheduled '{workflow.name}' for "
            f"{workflow.scheduled_at.strftime('%A %b %d at %I:%M %p') if workflow.scheduled_at else when} UTC"
        ),
        "next_step": "send_daily_report to run now, or wait for cron",
    }


def _send_daily_report(
    agent: WorkflowAgent,
    user_id: str,
    workflow_id: str | None = None,
    destination_id: str | None = None,
    email_to: str | None = None,
) -> dict:
    """Run the report workflow now (production send), or one-shot if ids given."""
    if workflow_id:
        return agent.run_now(workflow_id, user_id, mode="append")

    if not destination_id or not email_to:
        return {
            "needs_input": {"fields": ["workflow_id or (destination_id + email_to)"]},
            "next_step": "schedule_daily_report then send_daily_report(workflow_id)",
        }
    if not email_configured():
        return {"needs_input": {"fields": ["api_key"]}, "next_step": "configure_resend"}

    workflow = agent.create_daily_report_workflow(
        user_id=user_id,
        destination_id=destination_id,
        email_to=email_to,
        when="+1s",
        name="langfuse_daily_report_once",
        process_slug="langfuse_daily_report",
    )
    return agent.run_now(workflow.id, user_id, mode="append")


register(
    name="configure_resend",
    fn=_configure_resend,
    description=(
        "Configure Resend for Navbe HTML email reports. "
        "API key is encrypted at rest under ~/.navbe/email.json."
    ),
    parameters={
        "api_key": {"type": "string", "description": "Resend API key (re_...)"},
        "from_addr": {
            "type": "string",
            "description": "From address (default onboarding@resend.dev)",
        },
    },
)

register(
    name="configure_email",
    fn=_configure_email,
    description=(
        "Configure SMTP for Navbe HTML email reports (fallback). Prefer configure_resend. "
        "Password is encrypted at rest."
    ),
    parameters={
        "host": {"type": "string", "description": "SMTP host"},
        "port": {"type": "integer", "description": "SMTP port (default 587)"},
        "username": {"type": "string", "description": "SMTP username"},
        "password": {"type": "string", "description": "SMTP password / app password"},
        "from_addr": {"type": "string", "description": "From email address"},
        "use_tls": {"type": "boolean", "description": "Use STARTTLS (default true)"},
    },
)

register(
    name="preview_daily_report",
    fn=_preview_daily_report,
    description=(
        "Build the daily retailer HTML report from a DuckDB destination mart and save it "
        "under ~/.navbe/reports/ without sending email."
    ),
    parameters={
        "destination_id": {
            "type": "string",
            "description": "DuckDB destination that holds mart_retailer_token_cost_daily",
        },
    },
)

register(
    name="schedule_daily_report",
    fn=_schedule_daily_report,
    description=(
        "Schedule process langfuse_daily_report (default cron 0 23 * * * UTC) to email "
        "the HTML retailer report. Requires configure_resend (or configure_email) first."
    ),
    parameters={
        "destination_id": {"type": "string", "description": "DuckDB destination id"},
        "email_to": {
            "type": "string",
            "description": "Recipient email(s), comma-separated",
        },
        "when": {
            "type": "string",
            "description": "Cron or relative schedule (default 0 23 * * *)",
        },
        "name": {"type": "string", "description": "Workflow name"},
    },
)

register(
    name="send_daily_report",
    fn=_send_daily_report,
    description=(
        "Send the daily retailer HTML email now. Pass workflow_id from schedule_daily_report, "
        "or destination_id + email_to for a one-shot run."
    ),
    parameters={
        "workflow_id": {"type": "string", "description": "Existing report workflow id"},
        "destination_id": {"type": "string", "description": "DuckDB destination (one-shot)"},
        "email_to": {"type": "string", "description": "Recipients for one-shot send"},
    },
)
