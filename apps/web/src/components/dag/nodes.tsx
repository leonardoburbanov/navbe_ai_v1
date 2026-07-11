import { Handle, type NodeProps, Position } from "@xyflow/react";
import { statusColor } from "../../statusColors";

type NodeData = { label: string; status?: string };

function DagNodeShell({
  data,
  background,
}: {
  data: NodeData;
  background: string;
}) {
  const status = data.status ?? "idle";
  const color = statusColor(status);
  return (
    <div
      style={{
        border: `2px solid ${color}`,
        borderRadius: 8,
        padding: "8px 16px",
        background,
        minWidth: 160,
        textAlign: "center",
        boxShadow: status === "running" ? `0 0 12px ${color}` : "none",
        transition: "box-shadow 0.4s",
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div style={{ fontWeight: 600, fontSize: 13 }}>{data.label}</div>
      <div style={{ fontSize: 11, color }}>{status}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export function ConnectorNode({ data }: NodeProps) {
  return <DagNodeShell data={data as NodeData} background="#eff6ff" />;
}

export function TransformNode({ data }: NodeProps) {
  return <DagNodeShell data={data as NodeData} background="#fffbeb" />;
}

export function DestinationNode({ data }: NodeProps) {
  return <DagNodeShell data={data as NodeData} background="#f0fdf4" />;
}

export function ControlNode({ data }: NodeProps) {
  return <DagNodeShell data={data as NodeData} background="#f8fafc" />;
}
