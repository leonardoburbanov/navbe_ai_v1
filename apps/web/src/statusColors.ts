/** Shared status colors for badges and DAG nodes. */
export const STATUS_COLORS = {
  idle: "#94a3b8",
  running: "#3b82f6",
  succeeded: "#22c55e",
  failed: "#ef4444",
  skipped: "#d1d5db",
  paused: "#f59e0b",
  cancelled: "#78716c",
} as const;

export type NodeStatus =
  | "idle"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped";

export function statusColor(status: string | undefined): string {
  if (status && status in STATUS_COLORS) {
    return STATUS_COLORS[status as keyof typeof STATUS_COLORS];
  }
  if (status === "completed") return STATUS_COLORS.succeeded;
  return STATUS_COLORS.idle;
}
