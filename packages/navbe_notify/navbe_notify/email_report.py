"""HTML render + email send (Resend primary, SMTP fallback) for daily retailer report."""

from __future__ import annotations

import json
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from navbe_core.config import NAVBE_HOME
from navbe_core.models_report import ResendConfig, RetailerReportPayload, SmtpConfig
from navbe_core.secrets import decrypt, encrypt

_EMAIL_PATH = NAVBE_HOME / "email.json"
_SMTP_PATH = NAVBE_HOME / "email_smtp.json"  # legacy
_REPORTS_DIR = NAVBE_HOME / "reports"
_RESEND_URL = "https://api.resend.com/emails"


def _fmt_int(n: float | int) -> str:
    return f"{int(round(n)):,}"


def _fmt_cost(n: float) -> str:
    return f"${n:,.4f}"


def _fmt_pct(n: float | None) -> str:
    if n is None:
        return "—"
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.1f}%"


def _pct_color(n: float | None) -> str:
    if n is None:
        return "#64748b"
    if n > 0:
        return "#16a34a"
    if n < 0:
        return "#dc2626"
    return "#64748b"


def render_retailer_daily_html(payload: RetailerReportPayload) -> str:
    """Render a self-contained HTML email for the daily retailer report."""
    totals = payload.totals or {}
    rows_html = []
    for r in payload.rows:
        rows_html.append(
            f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-weight:600;">{r.retailer_id}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_int(r.today_traces)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_int(r.today_prompt_tokens)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_int(r.today_total_tokens)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_cost(r.today_cost)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;color:{_pct_color(r.dod_tokens_pct)};">{_fmt_pct(r.dod_tokens_pct)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;color:{_pct_color(r.dod_cost_pct)};">{_fmt_pct(r.dod_cost_pct)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_int(r.d7_avg_tokens)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_int(r.proj_next_7d_tokens)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_cost(r.proj_next_7d_cost)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_fmt_cost(r.proj_month_cost)}</td>
            </tr>
            """
        )
    body_rows = "".join(rows_html) or (
        '<tr><td colspan="11" style="padding:16px;color:#64748b;">No retailer-tagged data for this date.</td></tr>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Navbe daily retailer report</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="720" cellspacing="0" cellpadding="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,0.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:28px 32px;">
            <div style="font-size:28px;font-weight:800;letter-spacing:-0.03em;color:#fff;">Navbe</div>
            <div style="margin-top:6px;font-size:15px;color:#94a3b8;">Daily retailer tokens &amp; cost</div>
            <div style="margin-top:4px;font-size:13px;color:#64748b;">{payload.report_date}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 8px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
              <tr>
                <td style="padding:12px;background:#f8fafc;border-radius:8px;width:25%;">
                  <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:0.04em;">Retailers</div>
                  <div style="font-size:22px;font-weight:700;margin-top:4px;">{_fmt_int(totals.get("retailer_count", 0))}</div>
                </td>
                <td style="width:12px;"></td>
                <td style="padding:12px;background:#f8fafc;border-radius:8px;width:25%;">
                  <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:0.04em;">Today traces</div>
                  <div style="font-size:22px;font-weight:700;margin-top:4px;">{_fmt_int(totals.get("today_traces", 0))}</div>
                </td>
                <td style="width:12px;"></td>
                <td style="padding:12px;background:#f8fafc;border-radius:8px;width:25%;">
                  <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:0.04em;">Today tokens</div>
                  <div style="font-size:22px;font-weight:700;margin-top:4px;">{_fmt_int(totals.get("today_total_tokens", 0))}</div>
                </td>
                <td style="width:12px;"></td>
                <td style="padding:12px;background:#f8fafc;border-radius:8px;width:25%;">
                  <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:0.04em;">Today cost</div>
                  <div style="font-size:22px;font-weight:700;margin-top:4px;">{_fmt_cost(float(totals.get("today_cost", 0)))}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 24px 28px;">
            <div style="overflow-x:auto;">
              <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:12px;">
                <thead>
                  <tr style="background:#0f172a;color:#f8fafc;">
                    <th style="padding:10px 12px;text-align:left;">Retailer</th>
                    <th style="padding:10px 12px;text-align:right;">Traces</th>
                    <th style="padding:10px 12px;text-align:right;">Input tok</th>
                    <th style="padding:10px 12px;text-align:right;">Total tok</th>
                    <th style="padding:10px 12px;text-align:right;">Cost</th>
                    <th style="padding:10px 12px;text-align:right;">DoD tok</th>
                    <th style="padding:10px 12px;text-align:right;">DoD cost</th>
                    <th style="padding:10px 12px;text-align:right;">7d avg tok</th>
                    <th style="padding:10px 12px;text-align:right;">Proj 7d tok</th>
                    <th style="padding:10px 12px;text-align:right;">Proj 7d $</th>
                    <th style="padding:10px 12px;text-align:right;">Proj month $</th>
                  </tr>
                </thead>
                <tbody>
                  {body_rows}
                </tbody>
              </table>
            </div>
            <p style="margin:20px 0 0;font-size:11px;color:#94a3b8;line-height:1.5;">
              Projections use a 7-day average run-rate (heuristic, not ML).
              Month projection = month-to-date actual + avg × days remaining.
              Generated at {payload.generated_at}.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def save_report_preview(html: str, report_date: str) -> Path:
    """Write HTML under ~/.navbe/reports/ and return the path."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _REPORTS_DIR / f"retailer_daily_{report_date}.html"
    path.write_text(html, encoding="utf-8")
    return path


def save_resend_config(cfg: ResendConfig) -> None:
    """Persist Resend config with encrypted API key."""
    payload = {
        "provider": "resend",
        "api_key_enc": encrypt(cfg.api_key),
        "from_addr": cfg.from_addr,
    }
    _EMAIL_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_resend_config() -> ResendConfig | None:
    """Load Resend config from email.json when provider is resend."""
    if not _EMAIL_PATH.exists():
        return None
    raw = json.loads(_EMAIL_PATH.read_text(encoding="utf-8"))
    if raw.get("provider") != "resend":
        return None
    return ResendConfig(
        api_key=decrypt(raw["api_key_enc"]),
        from_addr=raw.get("from_addr") or "onboarding@resend.dev",
    )


def save_smtp_config(cfg: SmtpConfig) -> None:
    """Persist SMTP config with encrypted password."""
    payload = {
        "provider": "smtp",
        "host": cfg.host,
        "port": cfg.port,
        "username": cfg.username,
        "password_enc": encrypt(cfg.password),
        "from_addr": cfg.from_addr,
        "use_tls": cfg.use_tls,
    }
    _EMAIL_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Keep legacy path in sync for older readers.
    _SMTP_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_smtp_config() -> SmtpConfig | None:
    """Load SMTP config; return None if not configured."""
    path = _EMAIL_PATH if _EMAIL_PATH.exists() else _SMTP_PATH
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("provider") == "resend":
        return None
    if "password_enc" not in raw:
        return None
    return SmtpConfig(
        host=raw["host"],
        port=int(raw.get("port", 587)),
        username=raw["username"],
        password=decrypt(raw["password_enc"]),
        from_addr=raw["from_addr"],
        use_tls=bool(raw.get("use_tls", True)),
    )


def email_configured() -> bool:
    """True when Resend or SMTP credentials are stored."""
    return load_resend_config() is not None or load_smtp_config() is not None


def email_status_redacted() -> dict:
    """Public email config status without secrets."""
    if not _EMAIL_PATH.exists() and not _SMTP_PATH.exists():
        return {"configured": False, "provider": None, "from_addr": None}
    path = _EMAIL_PATH if _EMAIL_PATH.exists() else _SMTP_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    provider = raw.get("provider")
    if provider == "resend" or "api_key_enc" in raw:
        return {
            "configured": True,
            "provider": "resend",
            "from_addr": raw.get("from_addr"),
        }
    if "password_enc" in raw or provider == "smtp":
        return {
            "configured": True,
            "provider": "smtp",
            "from_addr": raw.get("from_addr"),
        }
    return {"configured": False, "provider": None, "from_addr": None}


def send_resend_html(
    to: list[str],
    subject: str,
    html: str,
    cfg: ResendConfig,
) -> dict:
    """Send HTML email via Resend HTTP API. Returns API JSON on success."""
    import httpx

    if not to:
        raise ValueError("email_to is empty")
    response = httpx.post(
        _RESEND_URL,
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": cfg.from_addr,
            "to": to,
            "subject": subject,
            "html": html,
        },
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Resend HTTP {response.status_code}: {response.text}")
    return response.json()


def probe_resend(cfg: ResendConfig) -> str:
    """Lightweight check that the API key is non-empty and looks like Resend."""
    if not cfg.api_key.startswith("re_"):
        return "api_key should start with re_"
    if not cfg.from_addr:
        return "from_addr required"
    return "ok"


def send_smtp_html(
    to: list[str],
    subject: str,
    html: str,
    smtp: SmtpConfig,
) -> None:
    """Send an HTML email via SMTP."""
    if not to:
        raise ValueError("email_to is empty")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp.from_addr
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(html, "html", "utf-8"))

    if smtp.use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
            server.starttls(context=context)
            if smtp.username:
                server.login(smtp.username, smtp.password)
            server.sendmail(smtp.from_addr, to, msg.as_string())
    else:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
            if smtp.username:
                server.login(smtp.username, smtp.password)
            server.sendmail(smtp.from_addr, to, msg.as_string())


def probe_smtp(cfg: SmtpConfig) -> str:
    """Best-effort SMTP handshake; returns 'ok' or an error string."""
    try:
        if cfg.use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as server:
                server.starttls(context=context)
                if cfg.username:
                    server.login(cfg.username, cfg.password)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as server:
                if cfg.username:
                    server.login(cfg.username, cfg.password)
        return "ok"
    except Exception as e:  # ponytail: surface any SMTP failure as string for MCP
        return str(e)


def send_html_email(to: list[str], subject: str, html: str) -> dict:
    """Send via Resend if configured, else SMTP. Returns {provider, ...}."""
    resend = load_resend_config()
    if resend is not None:
        result = send_resend_html(to, subject, html, resend)
        return {"provider": "resend", "result": result}
    smtp = load_smtp_config()
    if smtp is None:
        raise RuntimeError("Email not configured — call configure_resend or configure_email")
    send_smtp_html(to, subject, html, smtp)
    return {"provider": "smtp"}
