import { useCallback, useEffect, useState } from "react";
import { fetchProcesses } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { useProcessStore } from "../store/processStore";

type Props = {
  onOpenDag: (workflowId: string, slug: string) => void;
  onOpenRuns: (workflowId: string, slug: string) => void;
  onOpenReports: (workflowId: string, slug: string) => void;
};

export function ProcessesPage({ onOpenDag, onOpenRuns, onOpenReports }: Props) {
  const processes = useProcessStore((s) => s.processes);
  const setProcesses = useProcessStore((s) => s.setProcesses);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchProcesses()
      .then((r) => setProcesses(r.processes))
      .catch((e: Error) => {
        setProcesses([]);
        setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [setProcesses]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Processes</h2>
      {error && (
        <p style={{ color: "#ef4444" }}>
          Failed to load processes: {error}{" "}
          <button type="button" onClick={load}>
            Retry
          </button>
        </p>
      )}
      {loading && !error && (
        <p style={{ color: "#64748b" }}>Loading processes…</p>
      )}
      {!loading && !error && processes.length === 0 && (
        <div style={{ color: "#64748b", fontSize: 14, lineHeight: 1.6 }}>
          <p>No named processes yet.</p>
          <p>
            Create a Langfuse export via MCP with{" "}
            <code>create_langfuse_export_workflow</code> and{" "}
            <code>process_slug=langfuse_daily</code>, then refresh.
          </p>
          <p>
            If the daemon is down, start it with{" "}
            <code>uv run navbe daemon</code> on port 7700.
          </p>
        </div>
      )}
      {processes.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}
            >
              <th style={{ padding: 8 }}>Process</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Next run</th>
              <th style={{ padding: 8 }}>Watermark</th>
              <th style={{ padding: 8 }} />
            </tr>
          </thead>
          <tbody>
            {processes.map((p) => (
              <tr
                key={p.workflow_id}
                style={{ borderBottom: "1px solid #f1f5f9" }}
              >
                <td style={{ padding: 8 }}>
                  <div style={{ fontWeight: 600 }}>{p.process_slug}</div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>{p.name}</div>
                </td>
                <td style={{ padding: 8 }}>
                  <StatusBadge status={p.last_run?.status ?? p.status} />
                </td>
                <td style={{ padding: 8, fontSize: 13 }}>
                  {p.scheduled_at ?? "—"}
                </td>
                <td style={{ padding: 8, fontSize: 13 }}>
                  {p.watermark ?? "—"}
                </td>
                <td style={{ padding: 8 }}>
                  <button
                    type="button"
                    onClick={() => onOpenDag(p.workflow_id, p.process_slug)}
                  >
                    DAG
                  </button>{" "}
                  <button
                    type="button"
                    onClick={() => onOpenRuns(p.workflow_id, p.process_slug)}
                  >
                    Runs
                  </button>{" "}
                  <button
                    type="button"
                    onClick={() => onOpenReports(p.workflow_id, p.process_slug)}
                  >
                    Results
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
