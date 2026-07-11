import { Fragment, useEffect, useState } from "react";
import { type ReplayRow, fetchReplays } from "../api/client";

function diffBadge(row: ReplayRow): { label: string; color: string } {
  if (row.status_code >= 400) return { label: "error", color: "#ef4444" };
  if (row.compare?.identical) return { label: "identical", color: "#22c55e" };
  const n = row.compare?.diff_count ?? 0;
  return { label: `${n} diffs`, color: "#f59e0b" };
}

function JsonPane({ title, value }: { title: string; value: unknown }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>
        {title}
      </div>
      <pre
        style={{
          margin: 0,
          padding: 8,
          background: "#f8fafc",
          border: "1px solid #e2e8f0",
          borderRadius: 6,
          fontSize: 11,
          overflow: "auto",
          maxHeight: 240,
        }}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

type Props = {
  workflowId: string | null;
};

export function ReplaysPage({ workflowId }: Props) {
  const [rows, setRows] = useState<ReplayRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetchReplays(workflowId ?? undefined)
      .then((r) => setRows(r.replays ?? []))
      .catch((e: Error) => setError(e.message));
  }, [workflowId]);

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Replays</h2>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      {rows.length === 0 && !error ? (
        <p style={{ color: "#64748b" }}>
          No replay results yet. Use MCP <code>replay_trace_to_api</code> with a{" "}
          <code>destination_id</code>.
        </p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}
            >
              <th style={{ padding: 8 }}>Trace</th>
              <th style={{ padding: 8 }}>API</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Latency</th>
              <th style={{ padding: 8 }}>Diff</th>
              <th style={{ padding: 8 }}>When</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const badge = diffBadge(row);
              const open = expanded === row.id;
              return (
                <Fragment key={row.id}>
                  <tr
                    style={{
                      borderBottom: "1px solid #f1f5f9",
                      cursor: "pointer",
                    }}
                    onClick={() => setExpanded(open ? null : row.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setExpanded(open ? null : row.id);
                    }}
                  >
                    <td
                      style={{
                        padding: 8,
                        fontFamily: "monospace",
                        fontSize: 12,
                      }}
                    >
                      {row.trace_id}
                    </td>
                    <td
                      style={{
                        padding: 8,
                        fontSize: 12,
                        maxWidth: 220,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {row.api_url}
                    </td>
                    <td style={{ padding: 8 }}>{row.status_code}</td>
                    <td style={{ padding: 8, fontSize: 13 }}>
                      {Math.round(row.latency_ms)} ms
                    </td>
                    <td style={{ padding: 8 }}>
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: badge.color,
                          border: `1px solid ${badge.color}`,
                          borderRadius: 4,
                          padding: "2px 6px",
                        }}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td style={{ padding: 8, fontSize: 12 }}>{row.ts}</td>
                  </tr>
                  {open && (
                    <tr>
                      <td
                        colSpan={6}
                        style={{ padding: 12, background: "#fff" }}
                      >
                        <div style={{ display: "flex", gap: 12 }}>
                          <JsonPane
                            title="Original output"
                            value={row.original_output}
                          />
                          <JsonPane
                            title="API response"
                            value={row.response_body}
                          />
                        </div>
                        {(row.compare?.diffs?.length ?? 0) > 0 && (
                          <ul
                            style={{
                              fontSize: 12,
                              color: "#64748b",
                              marginTop: 8,
                            }}
                          >
                            {row.compare?.diffs?.slice(0, 20).map((d) => (
                              <li key={d.path}>
                                <code>{d.path}</code>:{" "}
                                {JSON.stringify(d.expected)} →{" "}
                                {JSON.stringify(d.actual)}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
