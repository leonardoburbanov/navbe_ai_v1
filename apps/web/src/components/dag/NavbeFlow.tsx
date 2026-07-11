import {
  Background,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  type NodeTypes,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import { useEffect, useState } from "react";
import "@xyflow/react/dist/style.css";
import { fetchGraph } from "../../api/client";
import { useDagStore } from "../../store/dagStore";
import { layoutGraph } from "./layout";
import {
  ConnectorNode,
  ControlNode,
  DestinationNode,
  TransformNode,
} from "./nodes";

const NODE_TYPES: NodeTypes = {
  connector: ConnectorNode,
  transform: TransformNode,
  destination: DestinationNode,
  control: ControlNode,
};

type Props = {
  workflowId: string;
  /** When set, node colors come from this run's SSE/seeded status. */
  runId?: string | null;
  selectedStep: string | null;
  onSelectStep: (step: string | null) => void;
  /** Compact height for the left sheet. */
  height?: number;
};

/** Fit viewport once React Flow has measured custom nodes. */
function FitViewOnReady() {
  const ready = useNodesInitialized();
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (ready) fitView({ padding: 0.2 });
  }, [ready, fitView]);
  return null;
}

/** Read-only React Flow canvas with live SSE status overlay. */
function NavbeFlowInner({
  workflowId,
  runId,
  selectedStep,
  onSelectStep,
  height = 560,
}: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const statusKey = runId || workflowId;
  // Stable selector — never `?? {}` (new object each render → setNodes loop → blank canvas).
  const nodeStatus = useDagStore((s) => s.nodeStatus[statusKey]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setLoading(true);
    setNodes([]);
    setEdges([]);
    fetchGraph(workflowId)
      .then(({ nodes: raw, edges: rawEdges }) => {
        if (cancelled) return;
        const asNodes: Node[] = raw.map((n) => ({
          id: n.id,
          type: n.type,
          data: { ...n.data, status: "idle" },
          position: n.position,
        }));
        const asEdges: Edge[] = rawEdges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          animated: e.animated ?? false,
        }));
        setNodes(layoutGraph(asNodes, asEdges));
        setEdges(asEdges);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId, setNodes, setEdges]);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        data: {
          ...n.data,
          status: nodeStatus?.[n.id] ?? "idle",
        },
        selected: selectedStep === n.id,
      })),
    );
  }, [nodeStatus, selectedStep, setNodes]);

  if (error) {
    return <p style={{ color: "#ef4444" }}>Failed to load graph: {error}</p>;
  }
  if (loading) {
    return (
      <div
        style={{
          height,
          border: "1px solid #e2e8f0",
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#64748b",
          background: "#f8fafc",
        }}
      >
        Loading DAG…
      </div>
    );
  }
  if (nodes.length === 0) {
    return (
      <div
        style={{
          height: Math.min(height, 240),
          border: "1px dashed #cbd5e1",
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#64748b",
          padding: 24,
          textAlign: "center",
        }}
      >
        This workflow has no graph nodes.
      </div>
    );
  }

  return (
    <div style={{ height, border: "1px solid #e2e8f0", borderRadius: 8 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onSelectStep(node.id)}
        onPaneClick={() => onSelectStep(null)}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <FitViewOnReady />
        <Background />
        <Controls showInteractive={false} />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}

/** Provider wrapper — required for useReactFlow / MiniMap context. */
export function NavbeFlow(props: Props) {
  return (
    <ReactFlowProvider>
      <NavbeFlowInner {...props} />
    </ReactFlowProvider>
  );
}
