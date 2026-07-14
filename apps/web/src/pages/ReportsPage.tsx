import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type AnalysisTemplate,
  type ProcessRow,
  type QueryResult,
  fetchCatalog,
  fetchProcesses,
  queryWorkflowDestination,
} from "../api/client";
import { Button } from "../components/ui/button";
import { Select } from "../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";

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
      <h2 className="mt-0 text-xl font-semibold">Reports</h2>
      <p className="mt-0 text-sm text-muted-foreground">
        Run analysis templates against a workflow destination (same queries as
        MCP <code>list_analysis_templates</code>). For email delivery, open{" "}
        <strong>Connectors → Destinations</strong> (email destination).
      </p>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label
          htmlFor="reports-workflow"
          className="flex flex-col gap-1 text-xs text-muted-foreground"
        >
          Workflow
          <Select
            id="reports-workflow"
            className="min-w-[220px]"
            value={selectedWorkflowId ?? ""}
            onChange={(e) => {
              setSelectedWorkflowId(e.target.value || null);
              setResult(null);
            }}
          >
            {processes.length === 0 && (
              <option value="">No workflows yet</option>
            )}
            {processes.map((p) => (
              <option key={p.workflow_id} value={p.workflow_id}>
                {p.slug || p.process_slug} — {p.name}
              </option>
            ))}
          </Select>
        </label>

        <label
          htmlFor="reports-template"
          className="flex flex-col gap-1 text-xs text-muted-foreground"
        >
          Template
          <Select
            id="reports-template"
            className="min-w-[280px]"
            value={selectedTemplateId ?? ""}
            onChange={(e) => {
              setSelectedTemplateId(e.target.value || null);
              setResult(null);
            }}
          >
            {templates.length === 0 && (
              <option value="">No DuckDB templates</option>
            )}
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </label>

        <Button
          type="button"
          onClick={() => runQuery(1)}
          disabled={loading || !selectedWorkflowId || !selectedTemplate}
        >
          {loading ? "Running…" : "Run template"}
        </Button>
      </div>

      {selectedTemplate?.description && (
        <p className="mt-0 text-sm text-muted-foreground">
          {selectedTemplate.description}
        </p>
      )}

      {error && <p className="text-destructive">{error}</p>}

      {result && result.total === 0 && (
        <p className="text-muted-foreground">
          No rows. Re-run the workflow so <code>refresh_retailer_mart</code>{" "}
          populates the mart, then try again.
        </p>
      )}

      {result && result.total > 0 && (
        <>
          <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {result.total} row{result.total === 1 ? "" : "s"} · page {page} of{" "}
              {totalPages}
            </span>
            <span className="inline-flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page <= 1 || loading}
                onClick={() => runQuery(page - 1)}
              >
                Prev
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page >= totalPages || loading}
                onClick={() => runQuery(page + 1)}
              >
                Next
              </Button>
            </span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                {result.columns.map((col) => (
                  <TableHead key={col}>{col}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.rows.map((row) => {
                const rowKey = row.map((c) => String(c ?? "")).join("|");
                return (
                  <TableRow key={rowKey}>
                    {result.columns.map((col, j) => (
                      <TableCell key={col} className="font-mono text-xs">
                        {row[j] == null ? "—" : String(row[j])}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </>
      )}
    </section>
  );
}
