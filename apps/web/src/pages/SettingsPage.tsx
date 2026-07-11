import { useCallback, useEffect, useState } from "react";
import {
  type EmailStatus,
  configureResendApi,
  fetchCatalog,
  fetchEmailStatus,
  previewDailyReportApi,
  scheduleDailyReportApi,
  sendDailyReportApi,
} from "../api/client";
import { CatalogPage } from "./CatalogPage";

type Props = {
  onOpenReports?: (templateId: string) => void;
};

/** Settings hub: integrations + Resend / daily report. */
export function SettingsPage({ onOpenReports }: Props) {
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [fromAddr, setFromAddr] = useState("onboarding@resend.dev");
  const [destinations, setDestinations] = useState<
    Array<{ id: string; name: string }>
  >([]);
  const [destinationId, setDestinationId] = useState("");
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
        const duck = c.destinations.filter((d) => d.type === "duckdb");
        setDestinations(duck.map((d) => ({ id: d.id, name: d.name })));
        setDestinationId((prev) => prev || duck[0]?.id || "");
      })
      .catch(() => setDestinations([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

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

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Settings</h2>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Connectors, destinations, and email for daily retailer reports.
      </p>

      <CatalogPage
        onOpenReports={onOpenReports ?? (() => undefined)}
      />

      <h3 style={{ marginTop: 32 }}>Email</h3>
      <div
        style={{
          padding: 16,
          border: "1px solid #e2e8f0",
          borderRadius: 10,
          background: "#fff",
          marginBottom: 24,
          maxWidth: 520,
        }}
      >
        <h3 style={{ marginTop: 0 }}>Resend</h3>
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
            style={{
              display: "block",
              width: "100%",
              marginTop: 4,
              padding: 8,
            }}
          />
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 12 }}>
          From address
          <input
            type="email"
            value={fromAddr}
            onChange={(e) => setFromAddr(e.target.value)}
            style={{
              display: "block",
              width: "100%",
              marginTop: 4,
              padding: 8,
            }}
          />
        </label>
        <button
          type="button"
          disabled={busy || !apiKey}
          onClick={() => {
            void (async () => {
              await run(() => configureResendApi(apiKey, fromAddr));
              setApiKey("");
            })();
          }}
        >
          Save Resend
        </button>
      </div>

      <div
        style={{
          padding: 16,
          border: "1px solid #e2e8f0",
          borderRadius: 10,
          background: "#fff",
          maxWidth: 520,
        }}
      >
        <h3 style={{ marginTop: 0 }}>Daily report</h3>
        <label style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
          Destination
          <select
            value={destinationId}
            onChange={(e) => setDestinationId(e.target.value)}
            style={{
              display: "block",
              width: "100%",
              marginTop: 4,
              padding: 8,
            }}
          >
            <option value="">Select…</option>
            {destinations.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
          Email to
          <input
            type="email"
            value={emailTo}
            onChange={(e) => setEmailTo(e.target.value)}
            style={{
              display: "block",
              width: "100%",
              marginTop: 4,
              padding: 8,
            }}
          />
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 12 }}>
          Cron (UTC)
          <input
            type="text"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            style={{
              display: "block",
              width: "100%",
              marginTop: 4,
              padding: 8,
            }}
          />
        </label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={busy || !destinationId}
            onClick={() => run(() => previewDailyReportApi(destinationId))}
          >
            Preview
          </button>
          <button
            type="button"
            disabled={busy || !destinationId || !emailTo}
            onClick={() =>
              run(() =>
                scheduleDailyReportApi({
                  destination_id: destinationId,
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
            disabled={busy || !destinationId}
            onClick={() =>
              run(() =>
                sendDailyReportApi({
                  destination_id: destinationId,
                  email_to: emailTo || undefined,
                }),
              )
            }
          >
            Send now
          </button>
        </div>
      </div>

      {err && <p style={{ color: "#ef4444", marginTop: 16 }}>{err}</p>}
      {msg && (
        <pre
          style={{
            marginTop: 16,
            fontSize: 11,
            background: "#f8fafc",
            padding: 12,
            borderRadius: 8,
            overflow: "auto",
          }}
        >
          {msg}
        </pre>
      )}
    </section>
  );
}
