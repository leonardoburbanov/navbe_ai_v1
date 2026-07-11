"""Pydantic models for the daily retailer HTML email report (Sprint 5 / MVP C)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetailerReportRow(BaseModel):
    """One retailer row in the daily report."""

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
    """Full daily retailer report payload for HTML rendering."""

    report_date: str
    generated_at: str
    rows: list[RetailerReportRow] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)


class SmtpConfig(BaseModel):
    """SMTP settings; password is plaintext only in memory."""

    host: str
    port: int = 587
    username: str
    password: str
    from_addr: str
    use_tls: bool = True
