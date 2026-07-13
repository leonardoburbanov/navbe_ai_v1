import { useEffect, useState } from "react";
import {
  type RunRow,
  pauseRunApi,
  resumeRunApi,
  stopRunApi,
} from "../api/client";
import { useDagStore } from "../store/dagStore";
import { NavbeFlow } from "./dag/NavbeFlow";
import { RunMetrics } from "./RunMetrics";
import { StatusBadge } from "./StatusBadge";

type Props = {
  run: RunRow;
  onClose: () => void;
  onUpdated?: () => void;
};

type Tab = "dag" | "report";

/** Left drawer: per-run DAG + report, with Pause / Resume / Stop. */
export function RunDetailSheet({ run, onClose, onUpdated }: Props) {
  const [tab, setTab] = useState<Tab>("dag");
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seedSteps = useDagStore((s) => s.seedSteps);
  const workflowId = run.workflow_id;
  const live =
    run.status === "running" ||
    run.status === "paused" ||
    run.control === "pause_requested" ||
    run.control === "cancel_requested";

  useEffect(() => {
    const steps = run.output?.steps;
    if (Array.isArray(steps) && run.run_id) {
      seedSteps(
        run.run_id,
        steps.filter(
          (s): s is { id: string; status: string } =>
            !!s &&
            typeof s === "object" &&
            typeof (s as { id?: unknown }).id === "string",
        ) as Array<{ id: string; status: string }>,
      );
    }
  }, [run.run_id, run.output, seedSteps]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onUpdated?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!workflowId) {
    return null;
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 40,
        display: "flex",
        pointerEvents: "none",
      }}
    >
      <button
        type="button"
        aria-label="Close run sheet"
        onClick={onClose}
        style={{
          flex: 1,
          border: "none",
          background: "rgba(15,23,42,0.25)",
          cursor: "pointer",
          pointerEvents: "auto",
        }}
      />
      <aside
        style={{
          width: "min(560px, 92vw)",
          height: "100%",
          background: "#fff",
          boxShadow: "4px 0 24px rgba(15,23,42,0.12)",
          display: "flex",
          flexDirection: "column",
          pointerEvents: "auto",
          order: -1,
        }}
      >
        <header
          style={{
            padding: "14px 16px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 8,
            }}
          >
            <div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>
                Run · {run.process_slug ?? "unnamed"}
                {live ? (
                  <span
                    style={{
                      marginLeft: 8,
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#2563eb",
                      letterSpacing: "0.04em",
                    }}
                  >
                    LIVE
                  </span>
                ) : null}
              </div>
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 11,
                  color: "#64748b",
                  marginTop: 2,
                }}
              >
                {run.run_id}
              </div>
            </div>
            <button type="button" onClick={onClose} style={{ fontSize: 18 }}>
              ×
            </button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <StatusBadge status={run.status} pulse={run.status === "running"} />
            {(run.status === "running" ||
              run.control === "pause_requested") && (
              <button
                type="button"
                disabled={busy}
                onClick={() => act(() => pauseRunApi(run.run_id))}
              >
                Pause
              </button>
            )}
            {run.status === "paused" && (
              <button
                type="button"
                disabled={busy}
                onClick={() => act(() => resumeRunApi(run.run_id))}
              >
                Resume
              </button>
            )}
            {(run.status === "running" || run.status === "paused") && (
              <button
                type="button"
                disabled={busy}
                onClick={() => act(() => stopRunApi(run.run_id))}
              >
                Stop
              </button>
            )}
          </div>
          {err && (
            <p style={{ color: "#ef4444", fontSize: 12, margin: 0 }}>{err}</p>
          )}
        </header>

        <div
          style={{
            display: "flex",
            gap: 4,
            padding: "8px 16px 0",
            borderBottom: "1px solid #e2e8f0",
          }}
        >
          {(
            [
              ["dag", "DAG"],
              ["report", "Report"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              style={{
                padding: "8px 12px",
                border: "none",
                borderBottom:
                  tab === key ? "2px solid #0f172a" : "2px solid transparent",
                background: "transparent",
                fontWeight: tab === key ? 700 : 500,
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
          {tab === "dag" && (
            <NavbeFlow
              workflowId={workflowId}
              runId={run.run_id}
              selectedStep={selectedStep}
              onSelectStep={setSelectedStep}
              height={420}
            />
          )}
          {tab === "report" && (
            <div>
              <RunMetrics output={run.output} />
              {typeof run.output?.report_date === "string" && (
                <p style={{ fontSize: 13, marginTop: 12 }}>
                  Report date: <strong>{run.output.report_date}</strong>
                  {run.output.email_sent === true
                    ? " · emailed"
                    : run.output.email_skipped === true
                      ? " · email skipped (no recipients)"
                      : run.output.preview_path
                        ? " · preview only"
                        : ""}
                </p>
              )}
              {typeof run.output?.preview_path === "string" && (
                <p style={{ fontSize: 12, color: "#64748b", wordBreak: "break-all" }}>
                  HTML: {run.output.preview_path}
                </p>
              )}
              {run.output?.totals != null && (
                <pre
                  style={{
                    marginTop: 12,
                    fontSize: 11,
                    background: "#f8fafc",
                    padding: 12,
                    borderRadius: 8,
                    overflow: "auto",
                  }}
                >
                  {JSON.stringify(run.output.totals, null, 2)}
                </pre>
              )}
              {run.error && (
                <pre
                  style={{
                    marginTop: 12,
                    fontSize: 11,
                    color: "#dc2626",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {run.error}
                </pre>
              )}
              {run.output?.compare_result != null && (
                <pre
                  style={{
                    marginTop: 12,
                    fontSize: 11,
                    background: "#f8fafc",
                    padding: 12,
                    borderRadius: 8,
                    overflow: "auto",
                  }}
                >
                  {JSON.stringify(run.output.compare_result, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
