"""Build daily retailer report payload from mart_retailer_token_cost_daily."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any

from navbe_core.models_report import RetailerReportPayload, RetailerReportRow


def _pct(today: float, yesterday: float) -> float | None:
    """Day-over-day percent change; None when yesterday is zero."""
    if yesterday == 0:
        return None if today == 0 else 100.0
    return (today - yesterday) / yesterday * 100.0


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def build_retailer_report_payload(
    con: Any,
    report_date: date | None = None,
) -> RetailerReportPayload:
    """Aggregate mart rows into DoD / 7d / projection metrics per retailer_id.

    ``con`` is an open DuckDB connection with ``mart_retailer_token_cost_daily``.
    """
    today = report_date or datetime.now(UTC).date()
    # If caller didn't pin a date and mart has no rows for UTC today yet,
    # use the latest mart date so end-of-day previews still show content.
    if report_date is None:
        latest = con.execute(
            "SELECT max(CAST(date AS DATE)) FROM mart_retailer_token_cost_daily"
        ).fetchone()
        if latest and latest[0] is not None:
            latest_d = _as_date(latest[0])
            if latest_d is not None and latest_d < today:
                today = latest_d

    yesterday = today - timedelta(days=1)
    window_start = today - timedelta(days=13)
    month_start = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_remaining = max(days_in_month - today.day, 0)

    rows_raw = con.execute(
        """
        SELECT
            CAST(retailer_id AS VARCHAR) AS retailer_id,
            CAST(date AS DATE) AS date,
            try_cast(trace_count AS BIGINT) AS trace_count,
            try_cast(prompt_tokens AS BIGINT) AS prompt_tokens,
            try_cast(completion_tokens AS BIGINT) AS completion_tokens,
            try_cast(total_tokens AS BIGINT) AS total_tokens,
            try_cast(total_cost AS DOUBLE) AS total_cost
        FROM mart_retailer_token_cost_daily
        WHERE CAST(date AS DATE) >= ?
          AND CAST(date AS DATE) <= ?
        """,
        [window_start, today],
    ).fetchall()

    # retailer_id -> date -> metrics
    by_retailer: dict[str, dict[date, dict[str, float]]] = {}
    for r in rows_raw:
        rid, d, traces, prompt, completion, total, cost = r
        day = _as_date(d)
        if rid is None or day is None:
            continue
        by_retailer.setdefault(str(rid), {})[day] = {
            "traces": float(traces or 0),
            "prompt": float(prompt or 0),
            "completion": float(completion or 0),
            "total": float(total or 0),
            "cost": float(cost or 0),
        }

    report_rows: list[RetailerReportRow] = []
    for rid, days in sorted(by_retailer.items()):
        t = days.get(today, {})
        y = days.get(yesterday, {})
        last7 = [
            days[d]
            for i in range(7)
            if (d := today - timedelta(days=i)) in days
        ]
        d7_sum_tokens = int(sum(m["total"] for m in last7))
        d7_sum_cost = float(sum(m["cost"] for m in last7))
        n7 = max(len(last7), 1)
        d7_avg_tokens = d7_sum_tokens / n7
        d7_avg_cost = d7_sum_cost / n7

        mtd_tokens = int(
            sum(m["total"] for d, m in days.items() if month_start <= d <= today)
        )
        mtd_cost = float(
            sum(m["cost"] for d, m in days.items() if month_start <= d <= today)
        )

        today_tokens = int(t.get("total", 0))
        today_cost = float(t.get("cost", 0))
        y_tokens = int(y.get("total", 0))
        y_cost = float(y.get("cost", 0))

        report_rows.append(
            RetailerReportRow(
                retailer_id=rid,
                today_traces=int(t.get("traces", 0)),
                today_prompt_tokens=int(t.get("prompt", 0)),
                today_completion_tokens=int(t.get("completion", 0)),
                today_total_tokens=today_tokens,
                today_cost=today_cost,
                yesterday_traces=int(y.get("traces", 0)),
                yesterday_total_tokens=y_tokens,
                yesterday_cost=y_cost,
                dod_tokens_pct=_pct(float(today_tokens), float(y_tokens)),
                dod_cost_pct=_pct(today_cost, y_cost),
                d7_sum_tokens=d7_sum_tokens,
                d7_sum_cost=d7_sum_cost,
                d7_avg_tokens=d7_avg_tokens,
                d7_avg_cost=d7_avg_cost,
                proj_next_7d_tokens=d7_avg_tokens * 7,
                proj_next_7d_cost=d7_avg_cost * 7,
                proj_month_tokens=mtd_tokens + d7_avg_tokens * days_remaining,
                proj_month_cost=mtd_cost + d7_avg_cost * days_remaining,
            )
        )

    totals = {
        "today_traces": sum(r.today_traces for r in report_rows),
        "today_total_tokens": sum(r.today_total_tokens for r in report_rows),
        "today_cost": sum(r.today_cost for r in report_rows),
        "proj_next_7d_tokens": sum(r.proj_next_7d_tokens for r in report_rows),
        "proj_next_7d_cost": sum(r.proj_next_7d_cost for r in report_rows),
        "retailer_count": len(report_rows),
    }

    return RetailerReportPayload(
        report_date=today.isoformat(),
        generated_at=datetime.now(UTC).isoformat(),
        rows=report_rows,
        totals=totals,
    )
