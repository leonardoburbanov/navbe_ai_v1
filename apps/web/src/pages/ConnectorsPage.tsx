import type { CSSProperties } from "react";
import { DestinationsPanel } from "../components/connectors/DestinationsPanel";
import { SourcesPanel } from "../components/connectors/SourcesPanel";

type Tab = "sources" | "destinations";

type Props = {
  tab: Tab;
  focusType?: string | null;
  onTabChange: (tab: Tab) => void;
  onOpenReports?: (templateId: string) => void;
};

const tabBtn = (active: boolean): CSSProperties => ({
  padding: "8px 14px",
  border: "none",
  borderBottom: active ? "2px solid #0f172a" : "2px solid transparent",
  background: "transparent",
  cursor: "pointer",
  fontWeight: active ? 700 : 500,
  color: active ? "#0f172a" : "#64748b",
});

/** Connectors hub: Sources | Destinations (email is a destination type). */
export function ConnectorsPage({
  tab,
  focusType,
  onTabChange,
  onOpenReports,
}: Props) {
  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Connectors</h2>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0 }}>
        Sources pull data; destinations store or deliver it (including email).
      </p>
      <nav style={{ display: "flex", gap: 4, marginBottom: 16 }}>
        <button
          type="button"
          style={tabBtn(tab === "sources")}
          onClick={() => onTabChange("sources")}
        >
          Sources
        </button>
        <button
          type="button"
          style={tabBtn(tab === "destinations")}
          onClick={() => onTabChange("destinations")}
        >
          Destinations
        </button>
      </nav>
      {tab === "sources" && <SourcesPanel />}
      {tab === "destinations" && (
        <DestinationsPanel
          focusType={focusType}
          onOpenReports={onOpenReports}
        />
      )}
    </section>
  );
}
