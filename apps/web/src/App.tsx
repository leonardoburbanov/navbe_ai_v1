import { type CSSProperties, useCallback, useEffect, useState } from "react";
import { handleSsePayload, useSSE } from "./api/sse";
import { HealthBar } from "./components/HealthBar";
import { ProcessSelector } from "./components/ProcessSelector";
import { CatalogPage } from "./pages/CatalogPage";
import { DagPage } from "./pages/DagPage";
import { ProcessesPage } from "./pages/ProcessesPage";
import { ReplaysPage } from "./pages/ReplaysPage";
import { ReportsPage } from "./pages/ReportsPage";
import { RunsPage } from "./pages/RunsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useDagStore } from "./store/dagStore";
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

function readUrlState(): { page: Page; workflowId: string | null } {
  const params = new URLSearchParams(window.location.search);
  const pageRaw = params.get("page") ?? "processes";
  const page = (
    PAGES.includes(pageRaw as Page) ? pageRaw : "processes"
  ) as Page;
  return { page, workflowId: params.get("workflow") };
}

function writeUrlState(page: Page, workflowId: string | null) {
  const params = new URLSearchParams();
  params.set("page", page);
  if (workflowId) params.set("workflow", workflowId);
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
  const [processSlug, setProcessSlug] = useState("");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [navHint, setNavHint] = useState<string | null>(null);
  const [sseOk, setSseOk] = useState(true);

  const patchStep = useDagStore((s) => s.patchStep);
  const resetRun = useDagStore((s) => s.resetRun);
  const patchStatus = useProcessStore((s) => s.patchStatus);

  useEffect(() => {
    writeUrlState(page, workflowId);
  }, [page, workflowId]);

  const onSse = useCallback(
    (e: MessageEvent) => {
      setSseOk(true);
      try {
        const event = JSON.parse(e.data) as {
          type?: string;
          workflow_id?: string;
          step?: string;
        };
        handleSsePayload(event, { patchStep, resetRun });
        if (event.workflow_id && event.type === "run.started") {
          patchStatus(event.workflow_id, "running");
        }
        if (event.workflow_id && event.type === "run.succeeded") {
          patchStatus(event.workflow_id, "completed");
        }
        if (event.workflow_id && event.type === "run.failed") {
          patchStatus(event.workflow_id, "failed");
        }
      } catch {
        // ignore malformed keepalive / non-JSON
      }
    },
    [patchStep, resetRun, patchStatus],
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

  const openDag = (id: string, slug: string) => {
    selectProcess(id, slug);
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
          <DagPage workflowId={workflowId} processSlug={processSlug} />
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
