import { useCallback, useEffect, useState } from "react";
import {
  type ProcessRow,
  type RunRow,
  fetchAllRuns,
  fetchProcesses,
  fetchRun,
  pauseRunApi,
  resumeRunApi,
  stopRunApi,
} from "../api/client";
import { RunDetailSheet } from "../components/RunDetailSheet";
import { StatusBadge } from "../components/StatusBadge";
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
import { formatDurationMs } from "../lib/formatDuration";

type Props = {
  processSlug: string | null;
  workflowId: string | null;
  initialRunId: string | null;
  onSelectProcess: (workflowId: string | null, processSlug: string) => void;
  onSelectRun: (runId: string | null) => void;
};

const PAGE_SIZE = 20;

/** Runs-first home: workflow filter + left sheet for DAG/report. */
export function RunsPage({
  processSlug,
  workflowId,
  initialRunId,
  onSelectProcess,
  onSelectRun,
}: Props) {
  const [processes, setProcesses] = useState<ProcessRow[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sheetRun, setSheetRun] = useState<RunRow | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(
    (pageNum: number) => {
      setLoading(true);
      setError(null);
      fetchAllRuns(processSlug || undefined, pageNum, PAGE_SIZE)
        .then((r) => {
          setRuns(r.runs ?? []);
          setPage(r.page ?? pageNum);
          setTotal(r.total ?? null);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    },
    [processSlug],
  );

  // Resolve slug once when deep-linked with workflow id only.
  // biome-ignore lint/correctness/useExhaustiveDependencies: avoid loop on onSelectProcess
  useEffect(() => {
    let cancelled = false;
    fetchProcesses()
      .then((r) => {
        if (cancelled) return;
        const list = r.processes ?? [];
        setProcesses(list);
        if (workflowId && !processSlug) {
          const p = list.find((x) => x.workflow_id === workflowId);
          if (p) onSelectProcess(p.workflow_id, p.slug || p.process_slug);
        }
      })
      .catch(() => {
        if (!cancelled) setProcesses([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId, processSlug]);

  useEffect(() => {
    load(1);
  }, [load]);

  useEffect(() => {
    if (!initialRunId) {
      setSheetRun(null);
      return;
    }
    const fromList = runs.find((r) => r.run_id === initialRunId);
    if (fromList) {
      setSheetRun(fromList);
      return;
    }
    fetchRun(initialRunId)
      .then((r) => setSheetRun(r))
      .catch(() => setSheetRun(null));
  }, [initialRunId, runs]);

  const sheetRunId = sheetRun?.run_id ?? null;
  const sheetRunning = sheetRun?.status === "running";

  // Refresh in-flight sheet when live so animation + status stay current.
  useEffect(() => {
    if (!sheetRunId || !sheetRunning) return;
    const id = window.setInterval(() => {
      fetchRun(sheetRunId)
        .then(setSheetRun)
        .catch(() => undefined);
      load(page);
    }, 2000);
    return () => window.clearInterval(id);
  }, [sheetRunId, sheetRunning, load, page]);

  const openRun = (r: RunRow) => {
    setSheetRun(r);
    onSelectRun(r.run_id);
    if (r.workflow_id) {
      onSelectProcess(r.workflow_id, r.slug ?? r.process_slug ?? "");
    }
  };

  const closeSheet = () => {
    setSheetRun(null);
    onSelectRun(null);
  };

  const refreshSheet = () => {
    load(page);
    if (sheetRun) {
      fetchRun(sheetRun.run_id)
        .then(setSheetRun)
        .catch(() => undefined);
    }
  };

  const act = async (runId: string, fn: () => Promise<unknown>) => {
    setBusyId(runId);
    try {
      await fn();
      refreshSheet();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const totalPages =
    total != null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="m-0 text-xl font-semibold">Runs</h2>
        <label
          htmlFor="runs-workflow-filter"
          className="text-sm text-muted-foreground"
        >
          Filter by workflow{" "}
          <Select
            id="runs-workflow-filter"
            className="ml-1.5 inline-flex w-auto min-w-[200px]"
            value={workflowId ?? ""}
            onChange={(e) => {
              const id = e.target.value;
              if (!id) {
                onSelectProcess(null, "");
                return;
              }
              const p = processes.find((x) => x.workflow_id === id);
              onSelectProcess(id, p?.slug || p?.process_slug || "");
            }}
          >
            <option value="">All workflows</option>
            {processes.map((p) => (
              <option key={p.workflow_id} value={p.workflow_id}>
                {p.slug || p.process_slug} — {p.name}
              </option>
            ))}
          </Select>
        </label>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        Click a run to open its DAG and report. New runs open automatically.
        Pause / Stop apply between steps.
      </p>

      {error && (
        <p className="text-destructive">
          {error}{" "}
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => load(page)}
          >
            Retry
          </Button>
        </p>
      )}
      {loading && !error && (
        <p className="text-muted-foreground">Loading runs…</p>
      )}
      {!loading && !error && runs.length === 0 && (
        <p className="text-muted-foreground">No runs yet.</p>
      )}

      {runs.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Workflow</TableHead>
                <TableHead>Run</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Completed</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((r) => (
                <TableRow
                  key={r.run_id}
                  data-state={
                    sheetRun?.run_id === r.run_id ? "selected" : undefined
                  }
                  className="cursor-pointer"
                  onClick={() => openRun(r)}
                >
                  <TableCell className="text-sm">
                    {r.slug ?? r.process_slug ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.run_id.slice(0, 8)}…
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={r.status}
                      pulse={r.status === "running"}
                    />
                  </TableCell>
                  <TableCell className="text-sm">{r.started_at}</TableCell>
                  <TableCell className="text-sm">
                    {formatDurationMs(r.duration_ms)}
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.completed_at ?? "—"}
                  </TableCell>
                  <TableCell
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    {r.status === "running" && (
                      <span className="inline-flex gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => pauseRunApi(r.run_id))
                          }
                        >
                          Pause
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="destructive"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => stopRunApi(r.run_id))
                          }
                        >
                          Stop
                        </Button>
                      </span>
                    )}
                    {r.status === "paused" && (
                      <span className="inline-flex gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => resumeRunApi(r.run_id))
                          }
                        >
                          Resume
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="destructive"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => stopRunApi(r.run_id))
                          }
                        >
                          Stop
                        </Button>
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-3 flex justify-between text-sm text-muted-foreground">
            <span>
              {total != null
                ? `${total} run${total === 1 ? "" : "s"} · page ${page}${totalPages ? ` of ${totalPages}` : ""}`
                : `Page ${page}`}
            </span>
            <span className="inline-flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page <= 1 || loading}
                onClick={() => load(page - 1)}
              >
                Prev
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={
                  loading ||
                  (totalPages != null
                    ? page >= totalPages
                    : runs.length < PAGE_SIZE)
                }
                onClick={() => load(page + 1)}
              >
                Next
              </Button>
            </span>
          </div>
        </>
      )}

      {sheetRun && (
        <RunDetailSheet
          run={sheetRun}
          onClose={closeSheet}
          onUpdated={refreshSheet}
        />
      )}
    </section>
  );
}
