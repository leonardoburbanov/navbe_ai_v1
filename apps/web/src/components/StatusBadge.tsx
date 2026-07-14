import { cn } from "@/lib/utils";
import { statusColor } from "../statusColors";
import { Badge } from "./ui/badge";

type Props = { status: string; pulse?: boolean };

/** Colored status pill for workflow/run rows. */
export function StatusBadge({ status, pulse = false }: Props) {
  const color = statusColor(status === "completed" ? "succeeded" : status);
  return (
    <Badge
      data-testid="status-badge"
      variant="outline"
      className={cn(
        "font-semibold text-foreground",
        pulse && "animate-[navbe-pulse_1.4s_ease-in-out_infinite]",
      )}
      style={{
        background: `${color}33`,
        borderColor: color,
        boxShadow: pulse ? `0 0 0 2px ${color}44` : undefined,
      }}
    >
      {status}
    </Badge>
  );
}
