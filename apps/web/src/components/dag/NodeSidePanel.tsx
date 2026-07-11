type Props = {
  step: string | null;
  status: string;
  onClose: () => void;
};

/** Slide-in panel for the selected DAG step. */
export function NodeSidePanel({ step, status, onClose }: Props) {
  if (!step) return null;
  return (
    <aside
      style={{
        width: 260,
        borderLeft: "1px solid #e2e8f0",
        padding: "1rem",
        background: "#fff",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <strong>{step}</strong>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <p style={{ fontSize: 13, color: "#64748b" }}>Status: {status}</p>
      <p style={{ fontSize: 12, color: "#94a3b8" }}>
        Step config and last-run metrics expand here in a later sprint.
      </p>
    </aside>
  );
}
