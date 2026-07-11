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
import { ProcessSelector } from "./components/ProcessSelector";
import { CatalogPage } from "./pages/CatalogPage";
import { DagPage } from "./pages/DagPage";
import { ProcessesPage } from "./pages/ProcessesPage";
import { ReplaysPage } from "./pages/ReplaysPage";
import { ReportsPage } from "./pages/ReportsPage";
import { RunsPage } from "./pages/RunsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useDagStore } from "./store/dagStore";
import { useLiveRunStore } from "./store/liveRunStore";
import { useProcessStore } from "./store/processStore";

type Page =
  | "processes"
  | "runs"
  | "catalog"
  | "dag"
  | "replays"
  | "reports"
  | "settings";

const PAGES: Page[] = [
  "processes",
  "runs",
  "dag",
  "catalog",
  "reports",
  "replays",
  "settings",
];

function readUrlState(): {
  page: Page;
  workflowId: string | null;
  runId: string | null;
} {
  const params = new URLSearchParams(window.location.search);
  const pageRaw = params.get("page") ?? "processes";
  const page = (
    PAGES.includes(pageRaw as Page) ? pageRaw : "processes"
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
  const [navHint, setNavHint] = useState<string | null>(null);
  const [sseOk, setSseOk] = useState(true);

  const patchStep = useDagStore((s) => s.patchStep);
  const resetRun = useDagStore((s) => s.resetRun);
  const patchStatus = useProcessStore((s) => s.patchStatus);
  const liveUpsert = useLiveRunStore((s) => s.upsert);
  const liveSetStep = useLiveRunStore((s) => s.setStep);
  const liveComplete = useLiveRunStore((s) => s.complete);
  const liveFail = useLiveRunStore((s) => s.fail);
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
          (r.runs ?? []).map((row) => ({
            runId: row.run_id,
            workflowId: row.workflow_id,
            processSlug: row.process_slug,
            status: "running" as const,
            step: row.step,
            startedAt: Date.parse(row.started_at) || Date.now(),
            updatedAt: Date.now(),
          })),
        );
      })
      .catch(() => {
        /* daemon may be down — HealthBar covers that */
      });
  }, [liveHydrate]);

  // Drop settled runs from the strip after 30s.
  useEffect(() => {
    const id = window.setInterval(() => {
      const now = Date.now();
      for (const r of Object.values(useLiveRunStore.getState().runs)) {
        if (r.status !== "running" && now - r.updatedAt > 30_000) {
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
    ],
  );

  useSSE("/events/sse", onSse, {
    onError: () => setSseOk(false),
    onOpen: () => setSseOk(true),
  });

  const selectProcess = (id: string, slug: string) => {
    setWorkflowId(id);
    setProcessSlug(slug);
    setNavHint(null);
  };

  const go = (next: Page) => {
    if ((next === "runs" || next === "dag") && !workflowId) {
      setNavHint(
        "Select a process in the header (or open one from Processes).",
      );
      setPage("processes");
      return;
    }
    setNavHint(null);
    setPage(next);
  };

  const openDag = (id: string, slug: string, nextRunId?: string) => {
    selectProcess(id, slug);
    setRunId(nextRunId ?? null);
    setPage("dag");
  };
  const openRuns = (id: string, slug: string) => {
    selectProcess(id, slug);
    setPage("runs");
  };
  const openReports = (id: string, slug: string, tplId?: string) => {
    selectProcess(id, slug);
    setTemplateId(tplId ?? null);
    setPage("reports");
  };
  const openReportsFromCatalog = (tplId: string) => {
    setTemplateId(tplId);
    setPage("reports");
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
          Control cockpit — processes, runs, DAG, integrations, reports
        </p>
        <HealthBar sseOk={sseOk} />
        <div style={{ marginBottom: 8 }}>
          <ProcessSelector workflowId={workflowId} onSelect={selectProcess} />
        </div>
        <LiveRunsStrip
          runs={liveRuns}
          onOpen={(id, slug, rid) => openDag(id, slug, rid)}
          onDismiss={liveDismiss}
        />
        {navHint && (
          <p style={{ color: "#b45309", fontSize: 13, margin: "0 0 8px" }}>
            {navHint}
          </p>
        )}
        <nav style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {(
            [
              ["processes", "Processes"],
              ["runs", "Runs"],
              ["dag", "DAG"],
              ["catalog", "Integrations"],
              ["reports", "Reports"],
              ["replays", "Replays"],
              ["settings", "Settings"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              style={navBtn(page === key)}
              onClick={() => go(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main
        style={{ padding: "1.5rem 2rem", maxWidth: 1100, margin: "0 auto" }}
      >
        {page === "processes" && (
          <ProcessesPage
            onOpenDag={openDag}
            onOpenRuns={openRuns}
            onOpenReports={openReports}
          />
        )}
        {page === "runs" && workflowId && (
          <RunsPage workflowId={workflowId} processSlug={processSlug} />
        )}
        {page === "runs" && !workflowId && (
          <p style={{ color: "#64748b" }}>Select a process to view runs.</p>
        )}
        {page === "catalog" && (
          <CatalogPage onOpenReports={openReportsFromCatalog} />
        )}
        {page === "reports" && (
          <ReportsPage workflowId={workflowId} initialTemplateId={templateId} />
        )}
        {page === "dag" && workflowId && (
          <DagPage
            workflowId={workflowId}
            processSlug={processSlug}
            runId={runId}
          />
        )}
        {page === "dag" && !workflowId && (
          <p style={{ color: "#64748b" }}>Select a process to view its DAG.</p>
        )}
        {page === "replays" && <ReplaysPage workflowId={workflowId} />}
        {page === "settings" && <SettingsPage />}
      </main>
    </div>
  );
}
