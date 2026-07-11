type Props = {
  newCount?: number;
  changed?: number;
  deleted?: number;
  traceCount?: number;
};

/** Compact run write metrics. */
export function RunMetrics({ newCount, changed, deleted, traceCount }: Props) {
  return (
    <span style={{ fontSize: 12, color: "#64748b" }}>
      {traceCount != null ? `${traceCount} traces · ` : ""}
      new {newCount ?? 0} · changed {changed ?? 0} · deleted {deleted ?? 0}
    </span>
  );
}
