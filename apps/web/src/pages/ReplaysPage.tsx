import { Fragment, useEffect, useState } from "react";
import { type ReplayRow, fetchReplays } from "../api/client";

type DiffEntry = {
  path: string;
  expected: unknown;
  actual: unknown;
  match?: boolean;
};

type ExperimentMessage = {
  index: number;
  expected: string | null;
  actual: string | null;
  match: boolean;
};

function diffBadge(row: ReplayRow): { label: string; color: string } {
  if (row.status_code >= 400) return { label: "error", color: "#ef4444" };
  const msgs = row.compare?.experiment_messages;
  if (msgs && msgs.length > 0 && row.compare?.messages_identical === false) {
    return { label: "message differs", color: "#f59e0b" };
  }
  if (row.compare?.identical) return { label: "identical", color: "#22c55e" };
  const n = row.compare?.diff_count ?? 0;
  return { label: `${n} field diffs`, color: "#f59e0b" };
}

function extractMessages(value: unknown): string[] {
  if (!value || typeof value !== "object") return [];
  const response = (value as { response?: unknown }).response;
  if (!Array.isArray(response)) return [];
  return response
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "text" in item) {
        const t = (item as { text: unknown }).text;
        return t == null ? "" : String(t);
      }
      return "";
    })
    .filter((t) => t.length > 0);
}

function experimentMessages(row: ReplayRow): ExperimentMessage[] {
  const fromCompare = row.compare?.experiment_messages;
  if (fromCompare && fromCompare.length > 0) {
    return fromCompare.map((m) => ({
      index: m.index,
      expected: m.expected ?? null,
      actual: m.actual ?? null,
      match: Boolean(m.match),
    }));
  }
  const orig = extractMessages(row.original_output);
  const act = extractMessages(row.response_body);
  const n = Math.max(orig.length, act.length, 1);
  const rows: ExperimentMessage[] = [];
  for (let i = 0; i < n; i++) {
    const expected = i < orig.length ? (orig[i] ?? null) : null;
    const actual = i < act.length ? (act[i] ?? null) : null;
    rows.push({
      index: i,
      expected,
      actual,
      match: expected === actual,
    });
  }
  return rows;
}

function MessagePane({
  title,
  text,
  changed,
}: {
  title: string;
  text: string | null;
  changed: boolean;
}) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div
        style={{
          fontWeight: 600,
          fontSize: 12,
          marginBottom: 4,
          color: changed ? "#b45309" : "#334155",
        }}
      >
        {title}
        {changed ? " · differs" : ""}
      </div>
      <pre
        style={{
          margin: 0,
          padding: 12,
          background: changed ? "#fffbeb" : "#f8fafc",
          border: `1px solid ${changed ? "#f59e0b" : "#e2e8f0"}`,
          borderRadius: 6,
          fontSize: 12,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          maxHeight: 280,
          overflow: "auto",
          lineHeight: 1.45,
        }}
      >
        {text ?? "(missing)"}
      </pre>
    </div>
  );
}

function DiffTable({ diffs }: { diffs: DiffEntry[] }) {
  if (diffs.length === 0) {
    return (
      <p style={{ fontSize: 12, color: "#64748b", margin: "8px 0 0" }}>
        No structural field differences.
      </p>
    );
  }
  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        marginTop: 8,
        fontSize: 12,
      }}
    >
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
          <th style={{ padding: "6px 8px" }}>Path</th>
          <th style={{ padding: "6px 8px" }}>Original (expected)</th>
          <th style={{ padding: "6px 8px" }}>Replay (actual)</th>
        </tr>
      </thead>
      <tbody>
        {diffs.slice(0, 40).map((d) => (
          <tr
            key={d.path}
            style={{ borderBottom: "1px solid #f1f5f9", verticalAlign: "top" }}
          >
            <td style={{ padding: "6px 8px", fontFamily: "monospace" }}>
              {d.path}
            </td>
            <td
              style={{
                padding: "6px 8px",
                background: "#fef2f2",
                maxWidth: 320,
              }}
            >
              <code style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {JSON.stringify(d.expected, null, 2)}
              </code>
            </td>
            <td
              style={{
                padding: "6px 8px",
                background: "#f0fdf4",
                maxWidth: 320,
              }}
            >
              <code style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {JSON.stringify(d.actual, null, 2)}
              </code>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Expandable experiment report: message texts + field-level diffs. */
function ExperimentReport({ row }: { row: ReplayRow }) {
  const messages = experimentMessages(row);
  const diffs = row.compare?.diffs ?? [];
  const msgsOk =
    row.compare?.messages_identical ?? messages.every((m) => m.match);
  const fieldsOk = Boolean(row.compare?.identical);
  const error = row.status_code >= 400;

  let verdict = "Experiment matched";
  let verdictColor = "#166534";
  let verdictBg = "#f0fdf4";
  if (error) {
    verdict = `API error ${row.status_code} — experiment failed`;
    verdictColor = "#991b1b";
    verdictBg = "#fef2f2";
  } else if (!msgsOk) {
    verdict = "Agent message text differs from original trace";
    verdictColor = "#92400e";
    verdictBg = "#fffbeb";
  } else if (!fieldsOk) {
    verdict = `${diffs.length} structural field difference(s) — messages match`;
    verdictColor = "#92400e";
    verdictBg = "#fffbeb";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div
        style={{
          padding: "10px 12px",
          borderRadius: 8,
          background: verdictBg,
          color: verdictColor,
          fontWeight: 600,
          fontSize: 13,
        }}
      >
        {verdict}
        <span style={{ fontWeight: 400, marginLeft: 8, opacity: 0.85 }}>
          {Math.round(row.latency_ms)} ms · status {row.status_code}
        </span>
      </div>

      <div>
        <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
          Experiment — agent messages
        </div>
        {messages.map((m) => (
          <div
            key={m.index}
            style={{ display: "flex", gap: 12, marginBottom: 8 }}
          >
            <MessagePane
              title={`Original · msg ${m.index}`}
              text={m.expected}
              changed={!m.match}
            />
            <MessagePane
              title={`Replay · msg ${m.index}`}
              text={m.actual}
              changed={!m.match}
            />
          </div>
        ))}
      </div>

      <div>
        <div style={{ fontWeight: 700, fontSize: 13 }}>
          Field differences ({diffs.length})
        </div>
        <DiffTable diffs={diffs} />
      </div>
    </div>
  );
}

type Props = {
  workflowId: string | null;
};

export function ReplaysPage({ workflowId }: Props) {
  const [rows, setRows] = useState<ReplayRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetchReplays(workflowId ?? undefined)
      .then((r) => setRows(r.replays ?? []))
      .catch((e: Error) => setError(e.message));
  }, [workflowId]);

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Replays — experiment report</h2>
      <p style={{ fontSize: 13, color: "#64748b", marginTop: -4 }}>
        Click a row to compare original Langfuse output vs replay API response.
      </p>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      {rows.length === 0 && !error ? (
        <p style={{ color: "#64748b" }}>
          No replay results yet. Use MCP <code>replay_trace_to_api</code> with a{" "}
          <code>destination_id</code>.
        </p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}
            >
              <th style={{ padding: 8 }}>Trace</th>
              <th style={{ padding: 8 }}>API</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Latency</th>
              <th style={{ padding: 8 }}>Experiment</th>
              <th style={{ padding: 8 }}>When</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const badge = diffBadge(row);
              const open = expanded === row.id;
              return (
                <Fragment key={row.id}>
                  <tr
                    style={{
                      borderBottom: "1px solid #f1f5f9",
                      cursor: "pointer",
                      background: open ? "#f8fafc" : undefined,
                    }}
                    onClick={() => setExpanded(open ? null : row.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setExpanded(open ? null : row.id);
                    }}
                  >
                    <td
                      style={{
                        padding: 8,
                        fontFamily: "monospace",
                        fontSize: 12,
                      }}
                    >
                      {row.trace_id}
                    </td>
                    <td
                      style={{
                        padding: 8,
                        fontSize: 12,
                        maxWidth: 220,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {row.api_url}
                    </td>
                    <td style={{ padding: 8 }}>{row.status_code}</td>
                    <td style={{ padding: 8, fontSize: 13 }}>
                      {Math.round(row.latency_ms)} ms
                    </td>
                    <td style={{ padding: 8 }}>
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: badge.color,
                          border: `1px solid ${badge.color}`,
                          borderRadius: 4,
                          padding: "2px 6px",
                        }}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td style={{ padding: 8, fontSize: 12 }}>{row.ts}</td>
                  </tr>
                  {open && (
                    <tr>
                      <td
                        colSpan={6}
                        style={{ padding: 12, background: "#fff" }}
                      >
                        <ExperimentReport row={row} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
