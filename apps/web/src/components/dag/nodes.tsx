import { cn } from "@/lib/utils";
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
  const running = status === "running";
  return (
    <div
      className={cn(
        "min-w-40 rounded-lg border-2 px-4 py-2 text-center transition-[box-shadow,border-color] duration-300",
        running && "animate-[navbe-node-pulse_1.2s_ease-in-out_infinite]",
      )}
      style={{
        borderColor: color,
        background,
        boxShadow: running ? `0 0 12px ${color}` : "none",
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="text-[13px] font-semibold">{data.label}</div>
      <div className="text-[11px]" style={{ color }}>
        {status}
      </div>
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
