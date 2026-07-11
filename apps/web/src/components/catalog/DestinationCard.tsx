import type { CSSProperties } from "react";

type Props = {
  name: string;
  type: string;
  schemaVersion: number | null;
  pathSummary: string | null;
  templateCount: number;
  onClick: () => void;
};

const card: CSSProperties = {
  textAlign: "left",
  padding: "14px 16px",
  border: "1px solid #e2e8f0",
  borderRadius: 10,
  background: "#fff",
  cursor: "pointer",
  width: "100%",
};

/** Clickable destination summary for the Integrations catalog. */
export function DestinationCard({
  name,
  type,
  schemaVersion,
  pathSummary,
  templateCount,
  onClick,
}: Props) {
  return (
    <button type="button" style={card} onClick={onClick}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{name}</div>
      <div style={{ fontSize: 12, color: "#64748b" }}>
        {type}
        {schemaVersion != null ? ` · schema v${schemaVersion}` : ""}
      </div>
      {pathSummary && (
        <div
          style={{
            fontSize: 12,
            color: "#94a3b8",
            marginTop: 6,
            fontFamily: "ui-monospace, monospace",
            wordBreak: "break-all",
          }}
        >
          {pathSummary}
        </div>
      )}
      <div style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
        {templateCount} template{templateCount === 1 ? "" : "s"}
      </div>
    </button>
  );
}
