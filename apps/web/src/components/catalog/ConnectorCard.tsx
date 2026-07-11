import type { CSSProperties } from "react";
import { StatusBadge } from "../StatusBadge";

type Props = {
  name: string;
  type: string;
  host: string;
  status: string;
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

/** Clickable connector summary for the Integrations catalog. */
export function ConnectorCard({ name, type, host, status, onClick }: Props) {
  return (
    <button type="button" style={card} onClick={onClick}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{name}</div>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
        {type} · {host || "—"}
      </div>
      <StatusBadge status={status} />
    </button>
  );
}
