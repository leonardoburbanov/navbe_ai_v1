import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { fetchHealth } from "../api/client";

type Props = {
  sseOk: boolean;
};

/** Daemon + SSE status strip. */
export function HealthBar({ sseOk }: Props) {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      fetchHealth()
        .then((r) => {
          if (!cancelled) setOnline(r.status === "ok");
        })
        .catch(() => {
          if (!cancelled) setOnline(false);
        });
    };
    tick();
    const id = window.setInterval(tick, 5000);
    const onFocus = () => tick();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const daemonLabel =
    online === null ? "checking…" : online ? "daemon online" : "daemon offline";
  const daemonOk = online === true;

  return (
    <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <span
          className={cn(
            "size-2 rounded-full",
            online === null && "bg-slate-400",
            daemonOk && "bg-green-600",
            online === false && "bg-red-600",
          )}
        />
        {daemonLabel}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className={cn(
            "size-2 rounded-full",
            sseOk ? "bg-green-600" : "bg-amber-500",
          )}
        />
        SSE {sseOk ? "connected" : "reconnecting"}
      </span>
      {online === false && (
        <span className="text-red-600">
          Start{" "}
          <code className="rounded bg-muted px-1">uv run navbe daemon</code> on
          :7700
        </span>
      )}
    </div>
  );
}
