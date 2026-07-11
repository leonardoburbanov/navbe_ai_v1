import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { fetchLiveRuns } from "./api/client";
import { handleSsePayload, useSSE } from "./api/sse";
import { HealthBar } from "./components/HealthBar";
import { LiveRunsStrip } from "./components/LiveRunsStrip";
import { ReportsPage } from "./pages/ReportsPage";
import { RunsPage } from "./pages/RunsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useDagStore } from "./store/dagStore";
import { useLiveRunStore } from "./store/liveRunStore";
import { useProcessStore } from "./store/processStore";

type Page = "runs" | "reports" | "settings";

const PAGES: Page[] = ["runs", "reports", "settings"];

function readUrlState(): {
  page: Page;
  workflowId: string | null;
  runId: string | null;
} {
  const params = new URLSearchParams(window.location.search);
  const pageRaw = params.get("page") ?? "runs";
  // Legacy deep links (dag/processes/replays/catalog) land on Runs.
  const page = (
    PAGES.includes(pageRaw as Page) ? pageRaw : "runs"
  ) as Page;
  return {
    page,
    workflowId: params.get("workflow"),
    runId: params.get("run"),
  };
}

function writeUrlState(
  page: Page,
  workflowId: string | null,
  runId: string | null,
) {
  const params = new URLSearchParams();
  params.set("page", page);
  if (workflowId) params.set("workflow", workflowId);
  if (runId) params.set("run", runId);
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

const navBtn = (active: boolean): CSSProperties => ({
  padding: "6px 12px",
  border: "none",
  borderBottom: active ? "2px solid #0f172a" : "2px solid transparent",
  background: "transparent",
  cursor: "pointer",
  fontWeight: active ? 700 : 500,
  color: active ? "#0f172a" : "#64748b",
});

export default function App() {
  const initial = readUrlState();
  const [page, setPage] = useState<Page>(initial.page);
  const [workflowId, setWorkflowId] = useState<string | null>(
    initial.workflowId,
  );
  const [runId, setRunId] = useState<string | null>(initial.runId);
  const [processSlug, setProcessSlug] = useState("");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [sseOk, setSseOk] = useState(true);

  const patchStep = useDagStore((s) => s.patchStep);
  const resetRun = useDagStore((s) => s.resetRun);
  const patchStatus = useProcessStore((s) => s.patchStatus);
  const liveUpsert = useLiveRunStore((s) => s.upsert);
  const liveSetStep = useLiveRunStore((s) => s.setStep);
  const liveComplete = useLiveRunStore((s) => s.complete);
  const liveFail = useLiveRunStore((s) => s.fail);
  const livePause = useLiveRunStore((s) => s.pause);
  const liveCancel = useLiveRunStore((s) => s.cancel);
  const liveDismiss = useLiveRunStore((s) => s.dismiss);
  const liveHydrate = useLiveRunStore((s) => s.hydrate);
  const liveRunsMap = useLiveRunStore((s) => s.runs);

  const liveRuns = useMemo(() => {
    const rows = Object.values(liveRunsMap);
    rows.sort((a, b) => b.updatedAt - a.updatedAt);
    return rows;
  }, [liveRunsMap]);

  useEffect(() => {
    writeUrlState(page, workflowId, runId);
  }, [page, workflowId, runId]);

  useEffect(() => {
    fetchLiveRuns()
      .then((r) => {
        liveHydrate(
          (r.runs ?? []).map((row) => {
            const st =
              row.status === "paused"
                ? ("paused" as const)
                : row.status === "cancelled"
                  ? ("cancelled" as const)
                  : ("running" as const);
            return {
              runId: row.run_id,
              workflowId: row.workflow_id,
              processSlug: row.process_slug,
              status: st,
              step: row.step,
              startedAt: Date.parse(row.started_at) || Date.now(),
              updatedAt: Date.now(),
            };
          }),
        );
      })
      .catch(() => {
        /* daemon may be down — HealthBar covers that */
      });
  }, [liveHydrate]);

  useEffect(() => {
    const id = window.setInterval(() => {
      const now = Date.now();
      for (const r of Object.values(useLiveRunStore.getState().runs)) {
        if (
          r.status !== "running" &&
          r.status !== "paused" &&
          now - r.updatedAt > 30_000
        ) {
          useLiveRunStore.getState().dismiss(r.runId);
        }
      }
    }, 5_000);
    return () => window.clearInterval(id);
  }, []);

  const onSse = useCallback(
    (e: MessageEvent) => {
      setSseOk(true);
      try {
        const event = JSON.parse(e.data) as {
          type?: string;
          workflow_id?: string;
          run_id?: string;
          process_slug?: string;
          step?: string;
        };
        handleSsePayload(
          event,
          { patchStep, resetRun },
          {
            upsert: liveUpsert,
            setStep: liveSetStep,
            complete: liveComplete,
            fail: liveFail,
            pause: livePause,
            cancel: liveCancel,
          },
          { patchStatus },
        );
      } catch {
        // ignore malformed keepalive / non-JSON
      }
    },
    [
      patchStep,
      resetRun,
      patchStatus,
      liveUpsert,
      liveSetStep,
      liveComplete,
      liveFail,
      livePause,
      liveCancel,
    ],
  );

  useSSE("/events/sse", onSse, {
    onError: () => setSseOk(false),
    onOpen: () => setSseOk(true),
  });

  const selectProcess = useCallback((id: string | null, slug: string) => {
    setWorkflowId(id);
    setProcessSlug(slug);
  }, []);

  const openRunSheet = (id: string, slug: string, nextRunId?: string) => {
    selectProcess(id, slug);
    setRunId(nextRunId ?? null);
    setPage("runs");
  };

  return (
    <div
      style={{
        fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
        minHeight: "100vh",
        background: "linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%)",
        color: "#0f172a",
      }}
    >
      <header
        style={{
          padding: "1.25rem 2rem 0",
          borderBottom: "1px solid #e2e8f0",
          background: "rgba(255,255,255,0.85)",
          backdropFilter: "blur(8px)",
        }}
      >
        <div
          style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.02em" }}
        >
          Navbe
        </div>
        <p style={{ margin: "4px 0 8px", color: "#64748b", fontSize: 14 }}>
          Control cockpit — runs, reports, settings
        </p>
        <HealthBar sseOk={sseOk} />
        <LiveRunsStrip
          runs={liveRuns}
          onOpen={(id, slug, rid) => openRunSheet(id, slug, rid)}
          onDismiss={liveDismiss}
        />
        <nav style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {(
            [
              ["runs", "Runs"],
              ["reports", "Reports"],
              ["settings", "Settings"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              style={navBtn(page === key)}
              onClick={() => setPage(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main
        style={{ padding: "1.5rem 2rem", maxWidth: 1100, margin: "0 auto" }}
      >
        {page === "runs" && (
          <RunsPage
            processSlug={processSlug || null}
            workflowId={workflowId}
            initialRunId={runId}
            onSelectProcess={selectProcess}
            onSelectRun={setRunId}
          />
        )}
        {page === "reports" && (
          <ReportsPage workflowId={workflowId} initialTemplateId={templateId} />
        )}
        {page === "settings" && (
          <SettingsPage
            onOpenReports={(tplId) => {
              setTemplateId(tplId);
              setPage("reports");
            }}
          />
        )}
      </main>
    </div>
  );
}
