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
    // Resolve slug once when deep-linked with workflow id only.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- avoid loop on onSelectProcess
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
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <h2 style={{ marginTop: 0, marginBottom: 0 }}>Runs</h2>
        <label style={{ fontSize: 13, color: "#64748b" }}>
          Filter by workflow{" "}
          <select
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
            style={{ minWidth: 200, padding: "4px 8px", marginLeft: 6 }}
          >
            <option value="">All workflows</option>
            {processes.map((p) => (
              <option key={p.workflow_id} value={p.workflow_id}>
                {p.slug || p.process_slug} — {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p style={{ fontSize: 13, color: "#64748b", marginTop: 8 }}>
        Click a run to open its DAG and report. Pause / Stop apply between
        steps.
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
        <p style={{ color: "#64748b" }}>No runs yet.</p>
      )}

      {runs.length > 0 && (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr
                style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}
              >
                <th style={{ padding: 8 }}>Workflow</th>
                <th style={{ padding: 8 }}>Run</th>
                <th style={{ padding: 8 }}>Status</th>
                <th style={{ padding: 8 }}>Started</th>
                <th style={{ padding: 8 }}>Duration</th>
                <th style={{ padding: 8 }}>Completed</th>
                <th style={{ padding: 8 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.run_id}
                  style={{
                    borderBottom: "1px solid #f1f5f9",
                    cursor: "pointer",
                    background:
                      sheetRun?.run_id === r.run_id ? "#f8fafc" : undefined,
                  }}
                  onClick={() => openRun(r)}
                >
                  <td style={{ padding: 8, fontSize: 13 }}>
                    {r.slug ?? r.process_slug ?? "—"}
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
                    <StatusBadge
                      status={r.status}
                      pulse={r.status === "running"}
                    />
                  </td>
                  <td style={{ padding: 8, fontSize: 13 }}>{r.started_at}</td>
                  <td style={{ padding: 8, fontSize: 13 }}>
                    {formatDurationMs(r.duration_ms)}
                  </td>
                  <td style={{ padding: 8, fontSize: 13 }}>
                    {r.completed_at ?? "—"}
                  </td>
                  <td
                    style={{ padding: 8 }}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    {r.status === "running" && (
                      <>
                        <button
                          type="button"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => pauseRunApi(r.run_id))
                          }
                        >
                          Pause
                        </button>{" "}
                        <button
                          type="button"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => stopRunApi(r.run_id))
                          }
                        >
                          Stop
                        </button>
                      </>
                    )}
                    {r.status === "paused" && (
                      <>
                        <button
                          type="button"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => resumeRunApi(r.run_id))
                          }
                        >
                          Resume
                        </button>{" "}
                        <button
                          type="button"
                          disabled={busyId === r.run_id}
                          onClick={() =>
                            act(r.run_id, () => stopRunApi(r.run_id))
                          }
                        >
                          Stop
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
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
