import { useCallback, useEffect, useState } from "react";
import {
  type WorkflowDetail,
  type WorkflowRow,
  fetchWorkflow,
  fetchWorkflows,
} from "../api/client";
import { NavbeFlow } from "../components/dag/NavbeFlow";
import { StatusBadge } from "../components/StatusBadge";

type Props = {
  workflowId: string | null;
  onSelectWorkflow: (workflowId: string | null, slug: string) => void;
  onOpenRuns: (workflowId: string, slug: string) => void;
  onRunNow?: (workflowId: string, slug: string) => void;
};

/** Workflow definitions list + right detail panel (read-only DAG). */
export function WorkflowsPage({
  workflowId,
  onSelectWorkflow,
  onOpenRuns,
  onRunNow,
}: Props) {
  const [rows, setRows] = useState<WorkflowRow[]>([]);
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchWorkflows()
      .then((r) => setRows(r.workflows ?? r.processes ?? []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!workflowId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    fetchWorkflow(workflowId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  const slugOf = (w: WorkflowRow) => w.slug || w.process_slug;

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 12,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 20 }}>Workflows</h2>
          <button
            type="button"
            onClick={load}
            style={{
              border: "1px solid #cbd5e1",
              background: "#fff",
              borderRadius: 6,
              padding: "4px 10px",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            Refresh
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: 12,
              background: "#fef2f2",
              color: "#991b1b",
              borderRadius: 8,
              marginBottom: 12,
            }}
          >
            {error}
            <button type="button" onClick={load} style={{ marginLeft: 8 }}>
              Retry
            </button>
          </div>
        )}

        {loading && <p style={{ color: "#64748b" }}>Loading workflows…</p>}

        {!loading && !error && rows.length === 0 && (
          <div
            style={{
              padding: 24,
              background: "#fff",
              borderRadius: 12,
              border: "1px solid #e2e8f0",
              color: "#475569",
            }}
          >
            <p style={{ marginTop: 0 }}>No workflows yet.</p>
            <p style={{ fontSize: 14 }}>
              Create via MCP{" "}
              <code>propose_workflow</code> then{" "}
              <code>confirm_workflow</code>, e.g. hint{" "}
              <code>&quot;monitor langfuse traces&quot;</code>.
            </p>
          </div>
        )}

        {rows.length > 0 && (
          <div
            style={{
              background: "#fff",
              borderRadius: 12,
              border: "1px solid #e2e8f0",
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                  <th style={{ padding: "10px 12px" }}>Name / slug</th>
                  <th style={{ padding: "10px 12px" }}>Trigger</th>
                  <th style={{ padding: "10px 12px" }}>Steps</th>
                  <th style={{ padding: "10px 12px" }}>Source → Dest</th>
                  <th style={{ padding: "10px 12px" }}>Last run</th>
                  <th style={{ padding: "10px 12px" }} />
                </tr>
              </thead>
              <tbody>
                {rows.map((w) => {
                  const slug = slugOf(w);
                  const active = w.workflow_id === workflowId;
                  const trigger =
                    w.cron_expression ||
                    w.trigger?.cron ||
                    (w.trigger?.type === "manual" ? "Manual" : "—");
                  return (
                    <tr
                      key={w.workflow_id}
                      style={{
                        borderTop: "1px solid #e2e8f0",
                        background: active ? "#eff6ff" : undefined,
                        cursor: "pointer",
                      }}
                      onClick={() => onSelectWorkflow(w.workflow_id, slug)}
                    >
                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ fontWeight: 600 }}>{slug}</div>
                        <div style={{ color: "#64748b", fontSize: 12 }}>{w.name}</div>
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <code style={{ fontSize: 12 }}>{trigger}</code>
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        {w.node_count ?? w.nodes?.length ?? "—"}
                      </td>
                      <td style={{ padding: "10px 12px", fontSize: 12 }}>
                        {w.connector_name || "—"} → {w.destination_name || "—"}
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        {w.last_run ? (
                          <StatusBadge status={w.last_run.status} />
                        ) : (
                          <span style={{ color: "#94a3b8" }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenRuns(w.workflow_id, slug);
                          }}
                          style={{
                            border: "none",
                            background: "transparent",
                            color: "#2563eb",
                            cursor: "pointer",
                            fontSize: 12,
                            marginRight: 8,
                          }}
                        >
                          Runs
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {workflowId && (
        <aside
          style={{
            width: 420,
            flexShrink: 0,
            background: "#fff",
            borderRadius: 12,
            border: "1px solid #e2e8f0",
            padding: 16,
            position: "sticky",
            top: 16,
            maxHeight: "calc(100vh - 120px)",
            overflow: "auto",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "start",
              marginBottom: 12,
            }}
          >
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>
                {detail?.slug || detail?.process_slug || workflowId.slice(0, 8)}
              </div>
              <div style={{ color: "#64748b", fontSize: 13 }}>{detail?.name}</div>
            </div>
            <button
              type="button"
              onClick={() => onSelectWorkflow(null, "")}
              style={{
                border: "none",
                background: "transparent",
                cursor: "pointer",
                color: "#64748b",
              }}
            >
              ✕
            </button>
          </div>

          <div style={{ fontSize: 13, marginBottom: 12, color: "#475569" }}>
            <div>
              <strong>Trigger:</strong>{" "}
              {detail?.cron_expression ||
                detail?.bindings?.trigger?.cron ||
                detail?.bindings?.trigger?.type ||
                "manual"}
            </div>
            <div>
              <strong>Source:</strong>{" "}
              {detail?.bindings?.connector_name || detail?.connector_name || "—"}
            </div>
            <div>
              <strong>Destination:</strong>{" "}
              {detail?.bindings?.destination_name ||
                detail?.destination_name ||
                "—"}
            </div>
            <div style={{ marginTop: 4 }}>
              <StatusBadge status={detail?.status || "scheduled"} />
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button
              type="button"
              onClick={() =>
                onOpenRuns(
                  workflowId,
                  detail?.slug || detail?.process_slug || "",
                )
              }
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                background: "#fff",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              View runs
            </button>
            {onRunNow && (
              <button
                type="button"
                onClick={() =>
                  onRunNow(
                    workflowId,
                    detail?.slug || detail?.process_slug || "",
                  )
                }
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "none",
                  background: "#0f172a",
                  color: "#fff",
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                Open runs
              </button>
            )}
          </div>

          <NavbeFlow
            workflowId={workflowId}
            selectedStep={selectedStep}
            onSelectStep={setSelectedStep}
            height={360}
          />
        </aside>
      )}
    </div>
  );
}
