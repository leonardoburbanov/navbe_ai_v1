# Sprint 5 — Daily HTML Email Retailer Report

End-of-day HTML email from `mart_retailer_token_cost_daily`: day-over-day comparison, 7-day averages, and simple run-rate projections per `retailer_id`. Delivered via SMTP (stdlib). Separate process `langfuse_daily_report` — does not replace `langfuse_daily` sync.

---

## Defaults

| Knob | Value |
| --- | --- |
| Delivery | SMTP (`smtplib`), secrets Fernet-encrypted under `~/.navbe` |
| Cron | `0 23 * * *` (23:00 UTC), process_slug `langfuse_daily_report` |
| Projections | 7-day average run-rate → next 7d and month remainder + MTD |
| HTML | Self-contained inline CSS; preview file under `~/.navbe/reports/` |

---

## Pydantic models (`navbe_core/models_report.py`)

```python
from __future__ import annotations
from pydantic import BaseModel, Field


class RetailerReportRow(BaseModel):
    retailer_id: str
    today_traces: int = 0
    today_prompt_tokens: int = 0
    today_completion_tokens: int = 0
    today_total_tokens: int = 0
    today_cost: float = 0.0
    yesterday_traces: int = 0
    yesterday_total_tokens: int = 0
    yesterday_cost: float = 0.0
    dod_tokens_pct: float | None = None
    dod_cost_pct: float | None = None
    d7_sum_tokens: int = 0
    d7_sum_cost: float = 0.0
    d7_avg_tokens: float = 0.0
    d7_avg_cost: float = 0.0
    proj_next_7d_tokens: float = 0.0
    proj_next_7d_cost: float = 0.0
    proj_month_tokens: float = 0.0
    proj_month_cost: float = 0.0


class RetailerReportPayload(BaseModel):
    report_date: str  # YYYY-MM-DD
    generated_at: str
    rows: list[RetailerReportRow] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)


class SmtpConfig(BaseModel):
    host: str
    port: int = 587
    username: str
    password: str  # plaintext in memory only; encrypt at rest
    from_addr: str
    use_tls: bool = True
```

---

## Transform (`navbe_transforms/retailer_report.py`)

`build_retailer_report_payload(con, report_date: date | None = None) -> RetailerReportPayload`

1. Read last 14 days from `mart_retailer_token_cost_daily`.
2. Per retailer: today / yesterday / 7d window metrics.
3. DoD % = `(today - yesterday) / yesterday * 100` when yesterday ≠ 0.
4. `proj_next_7d_* = d7_avg * 7`.
5. `proj_month_* = mtd_actual + d7_avg * days_remaining_in_month`.

---

## Email (`navbe_notify/email_report.py`)

- `render_retailer_daily_html(payload) -> str`
- `send_smtp_html(to: list[str], subject, html, smtp: SmtpConfig) -> None`
- `save_report_preview(html, report_date) -> Path` → `~/.navbe/reports/retailer_daily_{date}.html`
- `load_smtp_config() / save_smtp_config(SmtpConfig)` — password via `navbe_core.secrets.encrypt`

---

## LangGraph steps (`navbe_core/steps.py`)

### `build_retailer_report`

Open DuckDB from `dest_config` / default path; call transform; return `{report_payload, report_date}`.

### `send_email_report`

- If `mode == "preview"` or `preview_only`: write HTML file; publish `report.previewed`; do not send.
- Else: load SMTP; if missing → return `needs_input` shape (or raise clear error for MCP).
- Send to `state["email_to"]`; publish `report.sent` / `report.failed`.

### Graph IR

```json
{
  "entry": "build_retailer_report",
  "nodes": ["build_retailer_report", "send_email_report"],
  "edges": [["build_retailer_report", "send_email_report"]]
}
```

Registered in `SOURCES` or agent helper `create_daily_report_workflow`.

---

## MCP tools

| Tool | Behavior |
| --- | --- |
| `configure_email` | Validate required fields; optional SMTP connect probe; encrypt password; save |
| `preview_daily_report` | Resolve destination; build + render; save HTML; publish `report.previewed`; return path + summary |
| `schedule_daily_report` | Schedule graph workflow `langfuse_daily_report`, cron default `0 23 * * *`, input: destination_id, email_to |
| `send_daily_report` | `run_now` on report workflow (or one-shot graph) with production send |

---

## Events

| type | topic |
| --- | --- |
| `report.previewed` | `process.langfuse_daily_report` |
| `report.sent` | `process.langfuse_daily_report` |
| `report.failed` | `process.langfuse_daily_report` |

---

## Done signal

1. `configure_email` persists SMTP (password encrypted).
2. `preview_daily_report` writes HTML with DoD + projection columns when mart has data.
3. `schedule_daily_report` creates process `langfuse_daily_report` at 23:00 UTC.
4. `send_daily_report` sends mail; bus shows `report.sent`.
5. AGENTS.md documents MVP C; this plan file exists under `.cursor/plans/`.
