import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

type LiveRunRow = {
  runId: string;
  workflowId: string;
  processSlug: string | null;
  status: "running" | "completed" | "failed" | "paused" | "cancelled";
  step: string | null;
  startedAt: number;
};

type Props = {
  runs: LiveRunRow[];
  onOpen: (workflowId: string, processSlug: string, runId: string) => void;
  onDismiss: (runId: string) => void;
};

function ageLabel(startedAt: number): string {
  const s = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m`;
}

function statusColor(status: LiveRunRow["status"]): string {
  if (status === "failed" || status === "cancelled") return "#ef4444";
  if (status === "completed") return "#22c55e";
  if (status === "paused") return "#f59e0b";
  return "#3b82f6";
}

/** Compact strip of in-flight (and just-finished) runs under the nav. */
export function LiveRunsStrip({ runs, onOpen, onDismiss }: Props) {
  const visible = runs.slice(0, 5);
  if (visible.length === 0) return null;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 py-2">
      <span className="text-xs font-bold text-slate-600">Live</span>
      {visible.map((r) => {
        const pulse = r.status === "running";
        const color = statusColor(r.status);
        const label = r.processSlug || r.workflowId.slice(0, 8);
        return (
          <div
            key={r.runId}
            className={cn(
              "inline-flex h-8 items-center gap-1 rounded-md border bg-background px-2 text-xs shadow-sm",
              pulse && "animate-[navbe-pulse_1.4s_ease-in-out_infinite]",
            )}
            style={{
              borderColor: color,
              background: pulse ? "#eff6ff" : undefined,
              boxShadow: pulse ? `0 0 0 2px ${color}33` : undefined,
            }}
          >
            <button
              type="button"
              className="inline-flex cursor-pointer items-center gap-1.5 bg-transparent"
              onClick={() => onOpen(r.workflowId, r.processSlug || "", r.runId)}
            >
              <span
                className="size-2 shrink-0 rounded-full"
                style={{ background: color }}
              />
              <strong>{label}</strong>
              {r.status === "paused" && (
                <span className="text-amber-700">paused</span>
              )}
              {r.step && (
                <span className="text-muted-foreground">· {r.step}</span>
              )}
              <span className="text-muted-foreground">
                {ageLabel(r.startedAt)}
              </span>
            </button>
            {r.status !== "running" && r.status !== "paused" && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-5 text-muted-foreground hover:text-foreground"
                aria-label="Dismiss"
                onClick={() => onDismiss(r.runId)}
              >
                ×
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
