import { useEffect, useRef, useState } from "react";
import { type ProcessRow, fetchProcesses } from "../api/client";

type Props = {
  workflowId: string | null;
  onSelect: (workflowId: string, processSlug: string) => void;
};

/** Header dropdown to pick the active process for Runs / DAG. */
export function ProcessSelector({ workflowId, onSelect }: Props) {
  const [processes, setProcesses] = useState<ProcessRow[]>([]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    fetchProcesses()
      .then((r) => {
        setProcesses(r.processes);
        if (workflowId) {
          const p = r.processes.find((x) => x.workflow_id === workflowId);
          if (p) onSelectRef.current(p.workflow_id, p.process_slug);
        }
      })
      .catch(() => setProcesses([]));
  }, [workflowId]);

  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13,
        color: "#64748b",
      }}
    >
      Process
      <select
        value={workflowId ?? ""}
        onChange={(e) => {
          const id = e.target.value;
          const p = processes.find((x) => x.workflow_id === id);
          if (p) onSelect(p.workflow_id, p.process_slug);
        }}
        style={{ minWidth: 220, padding: "4px 8px" }}
      >
        <option value="">Select process…</option>
        {processes.map((p) => (
          <option key={p.workflow_id} value={p.workflow_id}>
            {p.process_slug} — {p.name}
          </option>
        ))}
      </select>
    </label>
  );
}
