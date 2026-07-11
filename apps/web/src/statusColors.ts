/** Shared status colors for badges and DAG nodes. */
export const STATUS_COLORS = {
  idle: "#94a3b8",
  running: "#3b82f6",
  succeeded: "#22c55e",
  failed: "#ef4444",
  skipped: "#d1d5db",
} as const;

export type NodeStatus = keyof typeof STATUS_COLORS;

export function statusColor(status: string | undefined): string {
  if (status && status in STATUS_COLORS) {
    return STATUS_COLORS[status as NodeStatus];
  }
  return STATUS_COLORS.idle;
}
