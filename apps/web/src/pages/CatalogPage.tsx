import { useEffect, useState } from "react";
import {
  type AnalysisTemplate,
  type CatalogResponse,
  fetchCatalog,
} from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { ConnectorCard } from "../components/catalog/ConnectorCard";
import { DestinationCard } from "../components/catalog/DestinationCard";
import { DetailDrawer } from "../components/catalog/DetailDrawer";

type Props = {
  onOpenReports: (templateId: string) => void;
};

type DrawerState =
  | { kind: "connector"; id: string }
  | { kind: "destination"; id: string }
  | { kind: "template"; template: AnalysisTemplate }
  | null;

const grid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
  gap: 12,
} as const;

export function CatalogPage({ onOpenReports }: Props) {
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerState>(null);

  useEffect(() => {
    fetchCatalog()
      .then(setCatalog)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return <p style={{ color: "#ef4444" }}>Failed to load catalog: {error}</p>;
  }
  if (!catalog)
    return <p style={{ color: "#64748b" }}>Loading integrations…</p>;

  const connector =
    drawer?.kind === "connector"
      ? catalog.connectors.find((c) => c.id === drawer.id)
      : null;
  const destination =
    drawer?.kind === "destination"
      ? catalog.destinations.find((d) => d.id === drawer.id)
      : null;

  const empty =
    catalog.connectors.length === 0 && catalog.destinations.length === 0;

  return (
    <section>
      <h3 style={{ marginTop: 0 }}>Integrations</h3>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0 }}>
        Connectors and destinations (create/rotate secrets via MCP; keys stay
        redacted here).
      </p>

      {empty && (
        <div style={{ color: "#64748b", fontSize: 14, lineHeight: 1.6 }}>
          <p>No connectors or destinations yet.</p>
          <p>
            Via MCP: <code>create_connector</code> then{" "}
            <code>create_destination</code>, or use{" "}
            <code>create_langfuse_export_workflow</code>.
          </p>
        </div>
      )}

      <h3>Connectors</h3>
      {catalog.connectors.length === 0 ? (
        <p style={{ color: "#64748b", fontSize: 14 }}>None configured.</p>
      ) : (
        <div style={grid}>
          {catalog.connectors.map((c) => (
            <ConnectorCard
              key={c.id}
              name={c.name}
              type={c.type}
              host={c.host}
              status={c.status}
              onClick={() => setDrawer({ kind: "connector", id: c.id })}
            />
          ))}
        </div>
      )}

      <h3 style={{ marginTop: 28 }}>Destinations</h3>
      {catalog.destinations.length === 0 ? (
        <p style={{ color: "#64748b", fontSize: 14 }}>None configured.</p>
      ) : (
        <div style={grid}>
          {catalog.destinations.map((d) => (
            <DestinationCard
              key={d.id}
              name={d.name}
              type={d.type}
              schemaVersion={d.schema_version}
              pathSummary={d.config_summary?.db_path ?? null}
              templateCount={d.templates.length}
              onClick={() => setDrawer({ kind: "destination", id: d.id })}
            />
          ))}
        </div>
      )}

      <h3 style={{ marginTop: 28 }}>Analysis templates</h3>
      {catalog.destinations.every((d) => d.templates.length === 0) ? (
        <p style={{ color: "#64748b", fontSize: 14 }}>
          Templates appear when a DuckDB destination is configured.
        </p>
      ) : (
        <div style={grid}>
          {catalog.destinations.flatMap((d) =>
            d.templates.map((t) => (
              <button
                key={`${d.id}-${t.id}`}
                type="button"
                onClick={() => setDrawer({ kind: "template", template: t })}
                style={{
                  textAlign: "left",
                  padding: "14px 16px",
                  border: "1px solid #e2e8f0",
                  borderRadius: 10,
                  background: "#fff",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontWeight: 700 }}>{t.name}</div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
                  {t.description}
                </div>
                <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 8 }}>
                  via {d.name}
                </div>
              </button>
            )),
          )}
        </div>
      )}

      <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 24 }}>
        Available types: connectors [{catalog.connector_types.join(", ")}] ·
        destinations [{catalog.destination_types.join(", ")}]
      </p>

      <DetailDrawer
        title={
          connector?.name ??
          destination?.name ??
          (drawer?.kind === "template" ? drawer.template.name : "Detail")
        }
        open={drawer != null}
        onClose={() => setDrawer(null)}
      >
        {connector && (
          <dl style={{ fontSize: 14, lineHeight: 1.7 }}>
            <dt style={{ color: "#64748b" }}>Type</dt>
            <dd style={{ margin: "0 0 12px" }}>{connector.type}</dd>
            <dt style={{ color: "#64748b" }}>Host</dt>
            <dd style={{ margin: "0 0 12px" }}>{connector.host || "—"}</dd>
            <dt style={{ color: "#64748b" }}>Status</dt>
            <dd style={{ margin: "0 0 12px" }}>
              <StatusBadge status={connector.status} />
            </dd>
            <dt style={{ color: "#64748b" }}>Id</dt>
            <dd style={{ margin: 0, fontFamily: "monospace", fontSize: 12 }}>
              {connector.id}
            </dd>
          </dl>
        )}
        {destination && (
          <>
            <dl style={{ fontSize: 14, lineHeight: 1.7 }}>
              <dt style={{ color: "#64748b" }}>Type</dt>
              <dd style={{ margin: "0 0 12px" }}>{destination.type}</dd>
              <dt style={{ color: "#64748b" }}>Schema</dt>
              <dd style={{ margin: "0 0 12px" }}>
                {destination.schema_version != null
                  ? `v${destination.schema_version}`
                  : "—"}
              </dd>
              <dt style={{ color: "#64748b" }}>Path</dt>
              <dd
                style={{
                  margin: "0 0 12px",
                  fontFamily: "monospace",
                  fontSize: 12,
                  wordBreak: "break-all",
                }}
              >
                {destination.config_summary?.db_path ?? "—"}
              </dd>
              <dt style={{ color: "#64748b" }}>Id</dt>
              <dd
                style={{
                  margin: "0 0 12px",
                  fontFamily: "monospace",
                  fontSize: 12,
                }}
              >
                {destination.id}
              </dd>
            </dl>
            {destination.templates.map((t) => (
              <div key={t.id} style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600 }}>{t.name}</div>
                <button
                  type="button"
                  style={{ marginTop: 6 }}
                  onClick={() => {
                    setDrawer(null);
                    onOpenReports(t.id);
                  }}
                >
                  Open in Reports
                </button>
              </div>
            ))}
          </>
        )}
        {drawer?.kind === "template" && (
          <>
            <p style={{ fontSize: 14, color: "#64748b" }}>
              {drawer.template.description}
            </p>
            <pre
              style={{
                fontSize: 11,
                background: "#f8fafc",
                padding: 12,
                borderRadius: 8,
                overflow: "auto",
                whiteSpace: "pre-wrap",
              }}
            >
              {drawer.template.query_example}
            </pre>
            <button
              type="button"
              onClick={() => {
                const id = drawer.template.id;
                setDrawer(null);
                onOpenReports(id);
              }}
            >
              Open in Reports
            </button>
          </>
        )}
      </DetailDrawer>
    </section>
  );
}
