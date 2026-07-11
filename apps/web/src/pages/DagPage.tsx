import { useState } from "react";
import { NavbeFlow } from "../components/dag/NavbeFlow";
import { NodeSidePanel } from "../components/dag/NodeSidePanel";
import { useDagStore } from "../store/dagStore";
import { useLiveRunStore } from "../store/liveRunStore";

type Props = {
  workflowId: string;
  processSlug: string;
  runId?: string | null;
};

export function DagPage({ workflowId, processSlug, runId }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const status =
    useDagStore((s) =>
      selected ? (s.nodeStatus[workflowId]?.[selected] ?? "idle") : "idle",
    ) ?? "idle";
  const live = useLiveRunStore((s) =>
    Object.values(s.runs).find(
      (r) =>
        r.workflowId === workflowId &&
        (runId ? r.runId === runId : r.status === "running"),
    ),
  );
  const isLive = Boolean(live && live.status === "running");

  return (
    <section>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 4,
        }}
      >
        <h2 style={{ margin: 0 }}>DAG — {processSlug || "unnamed"}</h2>
        {isLive && (
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: "#1d4ed8",
              border: "1px solid #3b82f6",
              background: "#eff6ff",
              borderRadius: 4,
              padding: "2px 8px",
              animation: "navbe-pulse 1.4s ease-in-out infinite",
            }}
          >
            LIVE{live?.step ? ` · ${live.step}` : ""}
          </span>
        )}
      </div>
      <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 0 }}>
        {workflowId}
        {runId ? ` · run ${runId}` : ""}
      </p>
      <div style={{ display: "flex", gap: 0 }}>
        <div style={{ flex: 1 }}>
          <NavbeFlow
            workflowId={workflowId}
            selectedStep={selected}
            onSelectStep={setSelected}
          />
        </div>
        <NodeSidePanel
          step={selected}
          status={status}
          onClose={() => setSelected(null)}
        />
      </div>
    </section>
  );
}
