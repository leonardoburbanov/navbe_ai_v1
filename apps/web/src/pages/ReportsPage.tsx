import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type AnalysisTemplate,
  type ProcessRow,
  type QueryResult,
  fetchCatalog,
  fetchProcesses,
  queryWorkflowDestination,
} from "../api/client";

const PAGE_SIZE = 20;

type Props = {
  workflowId: string | null;
  initialTemplateId?: string | null;
};

/**
 * Run analysis templates against a workflow destination and show a results table.
 */
export function ReportsPage({ workflowId, initialTemplateId }: Props) {
  const [processes, setProcesses] = useState<ProcessRow[]>([]);
  const [templates, setTemplates] = useState<AnalysisTemplate[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(
    workflowId,
  );
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    initialTemplateId ?? null,
  );
  const [result, setResult] = useState<QueryResult | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedWorkflowId(workflowId);
  }, [workflowId]);

  useEffect(() => {
    if (initialTemplateId) setSelectedTemplateId(initialTemplateId);
  }, [initialTemplateId]);

  useEffect(() => {
    fetchProcesses()
      .then((r) => {
        setProcesses(r.processes);
        setSelectedWorkflowId((prev) => {
          if (prev) return prev;
          const daily = r.processes.find(
            (p) => (p.slug || p.process_slug) === "langfuse_daily",
          );
          return daily?.workflow_id ?? r.processes[0]?.workflow_id ?? null;
        });
      })
      .catch(() => setProcesses([]));

    fetchCatalog()
      .then((c) => {
        const seen = new Map<string, AnalysisTemplate>();
        for (const d of c.destinations) {
          for (const t of d.templates) {
            if (t.query_example) seen.set(t.id, t);
          }
        }
        const list = [...seen.values()];
        setTemplates(list);
        setSelectedTemplateId((prev) => prev ?? list[0]?.id ?? null);
      })
      .catch(() => setTemplates([]));
  }, []);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );

  const runQuery = useCallback(
    async (pageNum: number) => {
      if (!selectedWorkflowId || !selectedTemplate?.query_example) {
        setError("Select a workflow and a template first.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await queryWorkflowDestination(
          selectedWorkflowId,
          selectedTemplate.query_example,
          pageNum,
          PAGE_SIZE,
        );
        setResult(data);
        setPage(pageNum);
      } catch (e) {
        setResult(null);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [selectedWorkflowId, selectedTemplate],
  );

  const totalPages =
    result && result.page_size > 0
      ? Math.max(1, Math.ceil(result.total / result.page_size))
      : 1;

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Reports</h2>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0 }}>
        Run analysis templates against a workflow destination (same queries as
        MCP <code>list_analysis_templates</code>). For email delivery, open{" "}
        <strong>Connectors → Destinations</strong> (email destination).
      </p>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          alignItems: "flex-end",
          marginBottom: 16,
        }}
      >
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#64748b" }}>Workflow</span>
          <select
            value={selectedWorkflowId ?? ""}
            onChange={(e) => {
              setSelectedWorkflowId(e.target.value || null);
              setResult(null);
            }}
            style={{ minWidth: 220, padding: "6px 8px" }}
          >
            {processes.length === 0 && (
              <option value="">No workflows yet</option>
            )}
            {processes.map((p) => (
              <option key={p.workflow_id} value={p.workflow_id}>
                {p.slug || p.process_slug} — {p.name}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#64748b" }}>Template</span>
          <select
            value={selectedTemplateId ?? ""}
            onChange={(e) => {
              setSelectedTemplateId(e.target.value || null);
              setResult(null);
            }}
            style={{ minWidth: 280, padding: "6px 8px" }}
          >
            {templates.length === 0 && (
              <option value="">No DuckDB templates</option>
            )}
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={() => runQuery(1)}
          disabled={loading || !selectedWorkflowId || !selectedTemplate}
          style={{ padding: "6px 14px", fontWeight: 600 }}
        >
          {loading ? "Running…" : "Run template"}
        </button>
      </div>

      {selectedTemplate?.description && (
        <p style={{ fontSize: 13, color: "#64748b", marginTop: 0 }}>
          {selectedTemplate.description}
        </p>
      )}

      {error && <p style={{ color: "#ef4444" }}>{error}</p>}

      {result && result.total === 0 && (
        <p style={{ color: "#64748b" }}>
          No rows. Re-run the workflow so <code>refresh_retailer_mart</code>{" "}
          populates the mart, then try again.
        </p>
      )}

      {result && result.total > 0 && (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 8,
              fontSize: 13,
              color: "#64748b",
            }}
          >
            <span>
              {result.total} row{result.total === 1 ? "" : "s"} · page {page} of{" "}
              {totalPages}
            </span>
            <span>
              <button
                type="button"
                disabled={page <= 1 || loading}
                onClick={() => runQuery(page - 1)}
              >
                Prev
              </button>{" "}
              <button
                type="button"
                disabled={page >= totalPages || loading}
                onClick={() => runQuery(page + 1)}
              >
                Next
              </button>
            </span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr
                  style={{
                    textAlign: "left",
                    borderBottom: "1px solid #e2e8f0",
                  }}
                >
                  {result.columns.map((col) => (
                    <th key={col} style={{ padding: 8, fontSize: 13 }}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => {
                  const rowKey = row.map((c) => String(c ?? "")).join("|");
                  return (
                    <tr
                      key={rowKey}
                      style={{ borderBottom: "1px solid #f1f5f9" }}
                    >
                      {result.columns.map((col, j) => (
                        <td
                          key={col}
                          style={{
                            padding: 8,
                            fontSize: 13,
                            fontFamily: "ui-monospace, monospace",
                          }}
                        >
                          {row[j] == null ? "—" : String(row[j])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
