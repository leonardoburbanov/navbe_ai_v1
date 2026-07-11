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
  const daemonColor =
    online === null ? "#94a3b8" : online ? "#16a34a" : "#dc2626";

  return (
    <div
      style={{
        display: "flex",
        gap: 16,
        alignItems: "center",
        fontSize: 12,
        color: "#64748b",
        marginBottom: 8,
      }}
    >
      <span>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: daemonColor,
            marginRight: 6,
          }}
        />
        {daemonLabel}
      </span>
      <span>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: sseOk ? "#16a34a" : "#f59e0b",
            marginRight: 6,
          }}
        />
        SSE {sseOk ? "connected" : "reconnecting"}
      </span>
      {online === false && (
        <span style={{ color: "#dc2626" }}>
          Start <code>uv run navbe daemon</code> on :7700
        </span>
      )}
    </div>
  );
}
