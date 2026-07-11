import { Fragment, useCallback, useEffect, useState } from "react";
import { type RunRow, fetchRuns } from "../api/client";
import { RunMetrics } from "../components/RunMetrics";
import { StatusBadge } from "../components/StatusBadge";

type Props = {
  workflowId: string;
  processSlug: string;
};

const PAGE_SIZE = 20;

export function RunsPage({ workflowId, processSlug }: Props) {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(
    (pageNum: number) => {
      setLoading(true);
      setError(null);
      fetchRuns(workflowId, pageNum, PAGE_SIZE)
        .then((r) => {
          setRuns(r.runs ?? []);
          setPage(r.page ?? pageNum);
          setTotal(r.total ?? null);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    },
    [workflowId],
  );

  useEffect(() => {
    setExpanded(null);
    load(1);
  }, [load]);

  const totalPages =
    total != null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Runs — {processSlug}</h2>
      <p style={{ fontSize: 12, color: "#94a3b8", marginTop: -8 }}>
        {workflowId}
      </p>
      {error && (
        <p style={{ color: "#ef4444" }}>
          {error}{" "}
          <button type="button" onClick={() => load(page)}>
            Retry
          </button>
        </p>
      )}
      {loading && !error && <p style={{ color: "#64748b" }}>Loading runs…</p>}
      {!loading && !error && runs.length === 0 && (
        <p style={{ color: "#64748b" }}>No runs yet for this process.</p>
      )}
      {runs.length > 0 && (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr
                style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}
              >
                <th style={{ padding: 8, width: 28 }} />
                <th style={{ padding: 8 }}>Run</th>
                <th style={{ padding: 8 }}>Status</th>
                <th style={{ padding: 8 }}>Started</th>
                <th style={{ padding: 8 }}>Completed</th>
                <th style={{ padding: 8 }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const open = expanded === r.run_id;
                return (
                  <Fragment key={r.run_id}>
                    <tr
                      style={{
                        borderBottom: open ? "none" : "1px solid #f1f5f9",
                        cursor: "pointer",
                      }}
                      onClick={() => setExpanded(open ? null : r.run_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setExpanded(open ? null : r.run_id);
                        }
                      }}
                      tabIndex={0}
                    >
                      <td style={{ padding: 8, color: "#94a3b8" }}>
                        {open ? "▾" : "▸"}
                      </td>
                      <td
                        style={{
                          padding: 8,
                          fontFamily: "monospace",
                          fontSize: 12,
                        }}
                      >
                        {r.run_id.slice(0, 8)}…
                      </td>
                      <td style={{ padding: 8 }}>
                        <StatusBadge status={r.status} />
                      </td>
                      <td style={{ padding: 8, fontSize: 13 }}>
                        {r.started_at}
                      </td>
                      <td style={{ padding: 8, fontSize: 13 }}>
                        {r.completed_at ?? "—"}
                      </td>
                      <td
                        style={{
                          padding: 8,
                          fontSize: 12,
                          color: "#dc2626",
                          maxWidth: 200,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {r.error ?? "—"}
                      </td>
                    </tr>
                    {open && (
                      <tr>
                        <td
                          colSpan={6}
                          style={{
                            padding: "8px 8px 16px 36px",
                            borderBottom: "1px solid #f1f5f9",
                            background: "#f8fafc",
                          }}
                        >
                          <div
                            style={{
                              fontSize: 12,
                              color: "#64748b",
                              marginBottom: 4,
                            }}
                          >
                            Metrics
                          </div>
                          <RunMetrics output={r.output} />
                          {r.error && (
                            <pre
                              style={{
                                marginTop: 8,
                                fontSize: 11,
                                whiteSpace: "pre-wrap",
                                color: "#dc2626",
                              }}
                            >
                              {r.error}
                            </pre>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: 12,
              fontSize: 13,
              color: "#64748b",
            }}
          >
            <span>
              {total != null
                ? `${total} run${total === 1 ? "" : "s"} · page ${page}${totalPages ? ` of ${totalPages}` : ""}`
                : `Page ${page}`}
            </span>
            <span>
              <button
                type="button"
                disabled={page <= 1 || loading}
                onClick={() => load(page - 1)}
              >
                Prev
              </button>{" "}
              <button
                type="button"
                disabled={
                  loading ||
                  (totalPages != null
                    ? page >= totalPages
                    : runs.length < PAGE_SIZE)
                }
                onClick={() => load(page + 1)}
              >
                Next
              </button>
            </span>
          </div>
        </>
      )}
    </section>
  );
}
