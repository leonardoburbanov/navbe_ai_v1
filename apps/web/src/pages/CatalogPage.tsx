import { useEffect, useState } from "react";
import { type CatalogResponse, fetchCatalog } from "../api/client";

type Props = {
  onOpenReports: (templateId: string) => void;
};

export function CatalogPage({ onOpenReports }: Props) {
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCatalog()
      .then(setCatalog)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p style={{ color: "#ef4444" }}>{error}</p>;
  if (!catalog) return <p style={{ color: "#64748b" }}>Loading catalog…</p>;

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Catalog</h2>

      <h3>Connector types</h3>
      <ul>
        {catalog.connector_types.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>

      <h3>Configured connectors</h3>
      {catalog.connectors.length === 0 ? (
        <p style={{ color: "#64748b" }}>None yet.</p>
      ) : (
        <ul>
          {catalog.connectors.map((c) => (
            <li key={c.id}>
              <strong>{c.name}</strong> ({c.type}) — {c.status} — {c.host}
            </li>
          ))}
        </ul>
      )}

      <h3>Destination types</h3>
      <ul>
        {catalog.destination_types.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>

      <h3>Configured destinations</h3>
      {catalog.destinations.length === 0 ? (
        <p style={{ color: "#64748b" }}>None yet.</p>
      ) : (
        <ul>
          {catalog.destinations.map((d) => (
            <li key={d.id}>
              <strong>{d.name}</strong> ({d.type})
              {d.schema_version != null ? ` · schema v${d.schema_version}` : ""}
              {d.templates.length > 0 && (
                <ul>
                  {d.templates.map((t) => (
                    <li key={t.id}>
                      Template: {t.name} — {t.description}{" "}
                      <button
                        type="button"
                        onClick={() => onOpenReports(t.id)}
                        style={{ fontSize: 12 }}
                      >
                        Open in Reports
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
