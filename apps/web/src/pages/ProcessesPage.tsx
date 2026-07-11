import { useEffect } from "react";
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

  useEffect(() => {
    fetchProcesses()
      .then((r) => setProcesses(r.processes))
      .catch(() => setProcesses([]));
  }, [setProcesses]);

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Processes</h2>
      {processes.length === 0 ? (
        <p style={{ color: "#64748b" }}>
          No named processes yet. Create a Langfuse export via MCP (
          <code>process_slug=langfuse_daily</code>).
        </p>
      ) : (
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
