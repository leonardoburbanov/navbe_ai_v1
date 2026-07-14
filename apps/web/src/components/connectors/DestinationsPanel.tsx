import { useCallback, useEffect, useState } from "react";
import {
  type EmailStatus,
  configureResendApi,
  fetchCatalog,
  fetchEmailStatus,
  previewDailyReportApi,
  scheduleDailyReportApi,
  sendDailyReportApi,
} from "../../api/client";

type Props = {
  focusType?: string | null;
  onOpenReports?: (templateId: string) => void;
};

/** Destinations tab: DuckDB/SQLite + email destination. */
export function DestinationsPanel({ focusType, onOpenReports }: Props) {
  const [destinations, setDestinations] = useState<
    Array<{
      id: string;
      type: string;
      name: string;
      config_summary?: Record<string, string | null | undefined>;
    }>
  >([]);
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [fromAddr, setFromAddr] = useState("onboarding@resend.dev");
  const [duckId, setDuckId] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [cron, setCron] = useState("0 23 * * *");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    fetchEmailStatus()
      .then((s) => {
        setStatus(s);
        if (s.from_addr) setFromAddr(s.from_addr);
      })
      .catch((e: Error) => setErr(e.message));
    fetchCatalog()
      .then((c) => {
        setDestinations(c.destinations ?? []);
        const duck = (c.destinations ?? []).filter((d) => d.type === "duckdb");
        setDuckId((prev) => prev || duck[0]?.id || "");
      })
      .catch(() => setDestinations([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (focusType === "email") {
      document.getElementById("destination-email")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [focusType]);

  const run = async (fn: () => Promise<Record<string, unknown>>) => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const r = await fn();
      setMsg(JSON.stringify(r, null, 2));
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const dataDests = destinations.filter((d) => d.type !== "email");
  const emailDest = destinations.find((d) => d.type === "email");
  const highlightEmail = focusType === "email";

  return (
    <div>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Destinations store results (DuckDB / SQLite) or deliver them (email).
      </p>
      {err && <p style={{ color: "#ef4444" }}>{err}</p>}
      {msg && (
        <pre
          style={{
            fontSize: 12,
            background: "#f8fafc",
            padding: 8,
            borderRadius: 6,
            overflow: "auto",
          }}
        >
          {msg}
        </pre>
      )}

      <h3>Data destinations</h3>
      {dataDests.length === 0 && (
        <p style={{ color: "#64748b", fontSize: 13 }}>
          No DuckDB/SQLite destinations yet. Create via MCP{" "}
          <code>create_destination</code>.
        </p>
      )}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {dataDests.map((d) => (
          <li
            key={d.id}
            style={{
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: 12,
              marginBottom: 8,
              background: "#fff",
            }}
          >
            <div style={{ fontWeight: 600 }}>{d.name}</div>
            <div style={{ fontSize: 12, color: "#64748b" }}>
              {d.type}
              {d.config_summary?.db_path
                ? ` · ${d.config_summary.db_path}`
                : ""}
            </div>
            {d.type === "duckdb" && onOpenReports && (
              <button
                type="button"
                style={{ marginTop: 8, fontSize: 12 }}
                onClick={() => onOpenReports("retailer_token_cost")}
              >
                Open reports
              </button>
            )}
          </li>
        ))}
      </ul>

      <h3 style={{ marginTop: 28 }}>Email destination</h3>
      <div
        id="destination-email"
        style={{
          padding: 16,
          border: highlightEmail ? "2px solid #2563eb" : "1px solid #e2e8f0",
          borderRadius: 10,
          background: "#fff",
          maxWidth: 520,
        }}
      >
        <p style={{ fontSize: 13, color: "#64748b", marginTop: 0 }}>
          Type <code>email</code>
          {emailDest ? ` · ${emailDest.name}` : " · not created yet"}
          . Configure Resend (or SMTP via MCP) — secrets stay encrypted.
        </p>
        <p style={{ fontSize: 13, color: "#64748b" }}>
          Status:{" "}
          {status == null
            ? "…"
            : status.configured
              ? `Configured (${status.provider ?? "resend"}) · from ${status.from_addr}`
              : "Not configured"}
        </p>
        <label style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
          API key
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={status?.configured ? "(unchanged)" : "re_…"}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 12 }}>
          From address
          <input
            type="email"
            value={fromAddr}
            onChange={(e) => setFromAddr(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <button
          type="button"
          disabled={busy || !apiKey.trim()}
          onClick={() =>
            run(() => configureResendApi(apiKey.trim(), fromAddr))
          }
          style={{
            padding: "8px 12px",
            background: "#0f172a",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: "pointer",
          }}
        >
          Save Resend
        </button>
        <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 8 }}>
          Enter the API key to save or rotate. SMTP: use MCP{" "}
          <code>configure_email</code>.
        </p>

        <h4 style={{ marginTop: 20 }}>Daily report actions</h4>
        <label style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
          DuckDB destination for mart
          <select
            value={duckId}
            onChange={(e) => setDuckId(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          >
            {dataDests
              .filter((d) => d.type === "duckdb")
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
          </select>
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
          Email to
          <input
            value={emailTo}
            onChange={(e) => setEmailTo(e.target.value)}
            placeholder="you@example.com"
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 12 }}>
          Cron
          <input
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={busy || !duckId}
            onClick={() => run(() => previewDailyReportApi(duckId))}
          >
            Preview
          </button>
          <button
            type="button"
            disabled={busy || !duckId || !emailTo}
            onClick={() =>
              run(() =>
                scheduleDailyReportApi({
                  destination_id: duckId,
                  email_to: emailTo,
                  when: cron,
                }),
              )
            }
          >
            Schedule
          </button>
          <button
            type="button"
            disabled={busy || !duckId}
            onClick={() =>
              run(() =>
                sendDailyReportApi({
                  destination_id: duckId,
                  email_to: emailTo || undefined,
                }),
              )
            }
          >
            Send now
          </button>
        </div>
      </div>
    </div>
  );
}
