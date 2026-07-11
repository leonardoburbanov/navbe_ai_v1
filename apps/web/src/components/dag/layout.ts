import { Graph, layout } from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

const NODE_W = 200;
const NODE_H = 60;

/** Top-to-bottom dagre layout; positions come from dagre, not the server. */
export function layoutGraph(nodes: Node[], edges: Edge[]): Node[] {
  const g = new Graph({ directed: true });
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 60 });

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }
  layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: {
        x: (pos?.x ?? 0) - NODE_W / 2,
        y: (pos?.y ?? 0) - NODE_H / 2,
      },
    };
  });
}
