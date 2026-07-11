import { type CSSProperties, useCallback, useState } from "react";
import { handleSsePayload, useSSE } from "./api/sse";
import { CatalogPage } from "./pages/CatalogPage";
import { DagPage } from "./pages/DagPage";
import { ProcessesPage } from "./pages/ProcessesPage";
import { RunsPage } from "./pages/RunsPage";
import { useDagStore } from "./store/dagStore";
import { useProcessStore } from "./store/processStore";

type Page = "processes" | "runs" | "catalog" | "dag";

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
  const [page, setPage] = useState<Page>("processes");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [processSlug, setProcessSlug] = useState("");

  const patchStep = useDagStore((s) => s.patchStep);
  const resetRun = useDagStore((s) => s.resetRun);
  const patchStatus = useProcessStore((s) => s.patchStatus);

  const onSse = useCallback(
    (e: MessageEvent) => {
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

  useSSE("/events/sse", onSse);

  const openDag = (id: string, slug: string) => {
    setWorkflowId(id);
    setProcessSlug(slug);
    setPage("dag");
  };
  const openRuns = (id: string, slug: string) => {
    setWorkflowId(id);
    setProcessSlug(slug);
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
        <p style={{ margin: "4px 0 12px", color: "#64748b", fontSize: 14 }}>
          Control cockpit — live processes, runs, catalog, and DAG
        </p>
        <nav style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            style={navBtn(page === "processes")}
            onClick={() => setPage("processes")}
          >
            Processes
          </button>
          <button
            type="button"
            style={navBtn(page === "runs")}
            onClick={() => setPage("runs")}
            disabled={!workflowId}
          >
            Runs
          </button>
          <button
            type="button"
            style={navBtn(page === "catalog")}
            onClick={() => setPage("catalog")}
          >
            Catalog
          </button>
          <button
            type="button"
            style={navBtn(page === "dag")}
            onClick={() => setPage("dag")}
            disabled={!workflowId}
          >
            DAG
          </button>
        </nav>
      </header>

      <main
        style={{ padding: "1.5rem 2rem", maxWidth: 1100, margin: "0 auto" }}
      >
        {page === "processes" && (
          <ProcessesPage onOpenDag={openDag} onOpenRuns={openRuns} />
        )}
        {page === "runs" && workflowId && (
          <RunsPage workflowId={workflowId} processSlug={processSlug} />
        )}
        {page === "catalog" && <CatalogPage />}
        {page === "dag" && workflowId && (
          <DagPage workflowId={workflowId} processSlug={processSlug} />
        )}
      </main>
    </div>
  );
}
