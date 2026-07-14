import { useCallback, useEffect, useState } from "react";
import {
  type ConnectorHubRow,
  createHubConnector,
  deleteHubConnector,
  deleteHubConnectorEnv,
  fetchHubConnectors,
  testHubConnector,
  upsertHubConnectorEnv,
} from "../../api/client";

/** Sources tab: Langfuse connectors + environments. */
export function SourcesPanel() {
  const [rows, setRows] = useState<ConnectorHubRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [envKey, setEnvKey] = useState("staging");
  const [envHost, setEnvHost] = useState("");
  const [envPk, setEnvPk] = useState("");
  const [envSk, setEnvSk] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    fetchHubConnectors()
      .then((r) => setRows(r.connectors ?? []))
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selectedRow = rows.find((r) => r.connector_id === selected) ?? null;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await fn();
      setMsg("Done");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Source connectors (e.g. Langfuse) with staging / testing / prod
        environments. Secrets are never shown after save.
      </p>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      {msg && <p style={{ color: "#16a34a", fontSize: 13 }}>{msg}</p>}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div>
          <h3 style={{ marginTop: 0 }}>Connectors</h3>
          {rows.length === 0 && (
            <p style={{ color: "#64748b", fontSize: 13 }}>
              No sources yet. Create one below or via MCP{" "}
              <code>create_connector</code>.
            </p>
          )}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {rows.map((c) => (
              <li
                key={c.connector_id}
                style={{
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                  padding: 12,
                  marginBottom: 8,
                  background: selected === c.connector_id ? "#eff6ff" : "#fff",
                  cursor: "pointer",
                }}
                onClick={() => setSelected(c.connector_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(c.connector_id);
                  }
                }}
              >
                <div style={{ fontWeight: 600 }}>{c.name}</div>
                <div style={{ fontSize: 12, color: "#64748b" }}>
                  {c.type} · {c.status}
                </div>
                <div
                  style={{
                    marginTop: 6,
                    display: "flex",
                    gap: 4,
                    flexWrap: "wrap",
                  }}
                >
                  {(c.envs ?? []).map((e) => (
                    <span
                      key={e.env_key}
                      style={{
                        fontSize: 11,
                        padding: "2px 6px",
                        borderRadius: 4,
                        background: e.is_default ? "#dbeafe" : "#f1f5f9",
                        border: "1px solid #cbd5e1",
                      }}
                    >
                      {e.env_key}
                      {e.is_default ? " ★" : ""}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>

          <h4>Create source</h4>
          <label style={{ display: "block", fontSize: 13, marginBottom: 6 }}>
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{
                display: "block",
                width: "100%",
                padding: 6,
                marginTop: 2,
              }}
            />
          </label>
          <label style={{ display: "block", fontSize: 13, marginBottom: 6 }}>
            Host
            <input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="https://cloud.langfuse.com"
              style={{
                display: "block",
                width: "100%",
                padding: 6,
                marginTop: 2,
              }}
            />
          </label>
          <label style={{ display: "block", fontSize: 13, marginBottom: 6 }}>
            Public key
            <input
              value={publicKey}
              onChange={(e) => setPublicKey(e.target.value)}
              style={{
                display: "block",
                width: "100%",
                padding: 6,
                marginTop: 2,
              }}
            />
          </label>
          <label style={{ display: "block", fontSize: 13, marginBottom: 8 }}>
            Secret key
            <input
              type="password"
              value={secretKey}
              onChange={(e) => setSecretKey(e.target.value)}
              style={{
                display: "block",
                width: "100%",
                padding: 6,
                marginTop: 2,
              }}
            />
          </label>
          <button
            type="button"
            disabled={busy || !name}
            onClick={() =>
              run(() =>
                createHubConnector({
                  name,
                  host,
                  public_key: publicKey,
                  secret_key: secretKey,
                }),
              )
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
            Create
          </button>
        </div>

        <div>
          <h3 style={{ marginTop: 0 }}>Environments</h3>
          {!selectedRow && (
            <p style={{ color: "#64748b", fontSize: 13 }}>
              Select a connector.
            </p>
          )}
          {selectedRow && (
            <>
              <div style={{ marginBottom: 12 }}>
                <strong>{selectedRow.name}</strong>
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() => testHubConnector(selectedRow.connector_id))
                    }
                  >
                    Test default
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() => deleteHubConnector(selectedRow.connector_id))
                    }
                    style={{ color: "#b91c1c" }}
                  >
                    Delete connector
                  </button>
                </div>
              </div>
              <ul style={{ listStyle: "none", padding: 0 }}>
                {(selectedRow.envs ?? []).map((e) => (
                  <li
                    key={e.env_key}
                    style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: 8,
                      padding: 10,
                      marginBottom: 8,
                      background: "#fff",
                      fontSize: 13,
                    }}
                  >
                    <div>
                      <strong>{e.env_key}</strong>
                      {e.is_default ? " (default)" : ""} · {e.status}
                    </div>
                    <div style={{ color: "#64748b" }}>
                      host: {e.public_config?.host || "—"} · secrets:{" "}
                      {e.has_secrets ? "••••" : "none"}
                    </div>
                    <div style={{ marginTop: 6, display: "flex", gap: 8 }}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          run(() =>
                            testHubConnector(
                              selectedRow.connector_id,
                              e.env_key,
                            ),
                          )
                        }
                      >
                        Test
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          run(() =>
                            deleteHubConnectorEnv(
                              selectedRow.connector_id,
                              e.env_key,
                            ),
                          )
                        }
                      >
                        Delete env
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              <h4>Add / update environment</h4>
              <label
                style={{ display: "block", fontSize: 13, marginBottom: 6 }}
              >
                Env key
                <input
                  value={envKey}
                  onChange={(e) => setEnvKey(e.target.value)}
                  placeholder="staging"
                  style={{
                    display: "block",
                    width: "100%",
                    padding: 6,
                    marginTop: 2,
                  }}
                />
              </label>
              <label
                style={{ display: "block", fontSize: 13, marginBottom: 6 }}
              >
                Host
                <input
                  value={envHost}
                  onChange={(e) => setEnvHost(e.target.value)}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: 6,
                    marginTop: 2,
                  }}
                />
              </label>
              <label
                style={{ display: "block", fontSize: 13, marginBottom: 6 }}
              >
                Public key
                <input
                  value={envPk}
                  onChange={(e) => setEnvPk(e.target.value)}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: 6,
                    marginTop: 2,
                  }}
                />
              </label>
              <label
                style={{ display: "block", fontSize: 13, marginBottom: 8 }}
              >
                Secret key
                <input
                  type="password"
                  value={envSk}
                  onChange={(e) => setEnvSk(e.target.value)}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: 6,
                    marginTop: 2,
                  }}
                />
              </label>
              <button
                type="button"
                disabled={busy || !envKey}
                onClick={() =>
                  run(() =>
                    upsertHubConnectorEnv(selectedRow.connector_id, envKey, {
                      host: envHost || undefined,
                      public_key: envPk || undefined,
                      secret_key: envSk || undefined,
                    }),
                  )
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
                Save environment
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
