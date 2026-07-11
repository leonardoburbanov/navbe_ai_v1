import { useState } from "react";
import { NavbeFlow } from "../components/dag/NavbeFlow";
import { NodeSidePanel } from "../components/dag/NodeSidePanel";
import { useDagStore } from "../store/dagStore";

type Props = {
  workflowId: string;
  processSlug: string;
};

export function DagPage({ workflowId, processSlug }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const status =
    useDagStore((s) =>
      selected ? (s.nodeStatus[workflowId]?.[selected] ?? "idle") : "idle",
    ) ?? "idle";

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>DAG — {processSlug || "unnamed"}</h2>
      <p style={{ fontSize: 12, color: "#94a3b8", marginTop: -8 }}>
        {workflowId}
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
