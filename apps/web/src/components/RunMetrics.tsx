type Props = {
  output?: Record<string, unknown> | null;
};

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

/** Compact metrics from a run's output payload. */
export function RunMetrics({ output }: Props) {
  if (!output || Object.keys(output).length === 0) {
    return <span style={{ fontSize: 12, color: "#94a3b8" }}>No metrics</span>;
  }

  const items: string[] = [];
  const traces = num(output.trace_count) ?? num(output.traces_written);
  const obs = num(output.observation_count) ?? num(output.observations_written);
  if (traces != null) items.push(`${traces} traces`);
  if (obs != null) items.push(`${obs} observations`);
  if (output.mart_refreshed === true) items.push("mart refreshed");
  if (output.email_sent === true) items.push("email sent");
  const reportPath = str(output.report_path) ?? str(output.html_path);
  if (reportPath) items.push(`report: ${reportPath}`);
  const err = str(output.error);
  if (err) items.push(`error: ${err}`);

  const known = new Set([
    "trace_count",
    "traces_written",
    "observation_count",
    "observations_written",
    "mart_refreshed",
    "email_sent",
    "report_path",
    "html_path",
    "error",
  ]);
  for (const [k, v] of Object.entries(output)) {
    if (known.has(k)) continue;
    if (
      typeof v === "boolean" ||
      typeof v === "number" ||
      typeof v === "string"
    ) {
      const s = String(v);
      if (s.length < 80) items.push(`${k}=${s}`);
    }
  }

  return (
    <span style={{ fontSize: 12, color: "#64748b", lineHeight: 1.5 }}>
      {items.length > 0
        ? items.join(" · ")
        : JSON.stringify(output).slice(0, 200)}
    </span>
  );
}
