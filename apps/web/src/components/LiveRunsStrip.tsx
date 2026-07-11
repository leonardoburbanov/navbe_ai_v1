type LiveRunRow = {
  runId: string;
  workflowId: string;
  processSlug: string | null;
  status: "running" | "completed" | "failed" | "paused" | "cancelled";
  step: string | null;
  startedAt: number;
};

type Props = {
  runs: LiveRunRow[];
  onOpen: (workflowId: string, processSlug: string, runId: string) => void;
  onDismiss: (runId: string) => void;
};

function ageLabel(startedAt: number): string {
  const s = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m`;
}

function statusColor(status: LiveRunRow["status"]): string {
  if (status === "failed" || status === "cancelled") return "#ef4444";
  if (status === "completed") return "#22c55e";
  if (status === "paused") return "#f59e0b";
  return "#3b82f6";
}

/** Compact strip of in-flight (and just-finished) runs under the nav. */
export function LiveRunsStrip({ runs, onOpen, onDismiss }: Props) {
  const visible = runs.slice(0, 5);
  if (visible.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        padding: "8px 0 12px",
        alignItems: "center",
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>
        Live
      </span>
      {visible.map((r) => {
        const pulse = r.status === "running";
        const color = statusColor(r.status);
        const label = r.processSlug || r.workflowId.slice(0, 8);
        return (
          <button
            key={r.runId}
            type="button"
            onClick={() => onOpen(r.workflowId, r.processSlug || "", r.runId)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              border: `1px solid ${color}`,
              background: pulse ? "#eff6ff" : "#f8fafc",
              color: "#0f172a",
              borderRadius: 6,
              padding: "4px 10px",
              fontSize: 12,
              cursor: "pointer",
              boxShadow: pulse ? `0 0 0 2px ${color}33` : "none",
              animation: pulse
                ? "navbe-pulse 1.4s ease-in-out infinite"
                : "none",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: color,
              }}
            />
            <strong>{label}</strong>
            {r.status === "paused" && (
              <span style={{ color: "#b45309" }}>paused</span>
            )}
            {r.step && <span style={{ color: "#64748b" }}>· {r.step}</span>}
            <span style={{ color: "#94a3b8" }}>{ageLabel(r.startedAt)}</span>
            {r.status !== "running" && r.status !== "paused" && (
              <button
                type="button"
                aria-label="Dismiss"
                onClick={(e) => {
                  e.stopPropagation();
                  onDismiss(r.runId);
                }}
                style={{
                  marginLeft: 4,
                  color: "#94a3b8",
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: 14,
                }}
              >
                ×
              </button>
            )}
          </button>
        );
      })}
      <style>
        {"@keyframes navbe-pulse { 0%,100%{opacity:1} 50%{opacity:0.65} }"}
      </style>
    </div>
  );
}
