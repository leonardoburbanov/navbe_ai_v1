import { statusColor } from "../statusColors";

type Props = { status: string };

/** Colored status pill for process/run rows. */
export function StatusBadge({ status }: Props) {
  const color = statusColor(status === "completed" ? "succeeded" : status);
  return (
    <span
      data-testid="status-badge"
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        color: "#0f172a",
        background: `${color}33`,
        border: `1px solid ${color}`,
      }}
    >
      {status}
    </span>
  );
}
