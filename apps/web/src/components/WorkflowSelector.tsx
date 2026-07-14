import { useEffect, useRef, useState } from "react";
import { type WorkflowRow, fetchWorkflows } from "../api/client";

type Props = {
  workflowId: string | null;
  onSelect: (workflowId: string, slug: string) => void;
};

/** Header filter: pick a workflow by slug. */
export function WorkflowSelector({ workflowId, onSelect }: Props) {
  const [rows, setRows] = useState<WorkflowRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    let cancelled = false;
    fetchWorkflows()
      .then((r) => {
        if (cancelled) return;
        const list = r.workflows ?? r.processes ?? [];
        setRows(list);
        if (!workflowId && list.length === 1) {
          const p = list[0];
          if (p) onSelectRef.current(p.workflow_id, p.slug || p.process_slug);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  return (
    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      <span style={{ color: "#64748b" }}>Workflow</span>
      <select
        value={workflowId ?? ""}
        onChange={(e) => {
          const id = e.target.value;
          const p = rows.find((x) => x.workflow_id === id);
          if (p) onSelect(p.workflow_id, p.slug || p.process_slug);
        }}
        style={{
          padding: "4px 8px",
          borderRadius: 6,
          border: "1px solid #cbd5e1",
          minWidth: 180,
        }}
      >
        <option value="">All workflows</option>
        {rows.map((p) => (
          <option key={p.workflow_id} value={p.workflow_id}>
            {p.slug || p.process_slug} — {p.name}
          </option>
        ))}
      </select>
      {error && <span style={{ color: "#ef4444", fontSize: 12 }}>{error}</span>}
    </label>
  );
}

/** @deprecated use WorkflowSelector */
export const ProcessSelector = WorkflowSelector;
