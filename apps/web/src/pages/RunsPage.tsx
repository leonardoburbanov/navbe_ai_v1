import { useEffect, useState } from "react";
import { type RunRow, fetchRuns } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";

type Props = {
  workflowId: string;
  processSlug: string;
};

export function RunsPage({ workflowId, processSlug }: Props) {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRuns(workflowId)
      .then((r) => setRuns(r.runs ?? []))
      .catch((e: Error) => setError(e.message));
  }, [workflowId]);

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Runs — {processSlug}</h2>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      {runs.length === 0 && !error ? (
        <p style={{ color: "#64748b" }}>No runs yet.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}
            >
              <th style={{ padding: 8 }}>Run</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Started</th>
              <th style={{ padding: 8 }}>Completed</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td
                  style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}
                >
                  {r.run_id}
                </td>
                <td style={{ padding: 8 }}>
                  <StatusBadge status={r.status} />
                </td>
                <td style={{ padding: 8, fontSize: 13 }}>{r.started_at}</td>
                <td style={{ padding: 8, fontSize: 13 }}>
                  {r.completed_at ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
