# Sprint 3 — Control UI v0 + DAG Canvas

Vite + React + TypeScript in `apps/web`. Four views: Processes, Runs, Catalog, DAG canvas. The daemon SSE stream already exists; this sprint adds the REST endpoints and the UI that consumes them.

---

## New daemon REST endpoints (navbe_api/app.py)

```python
# GET /api/processes
# Returns all workflows with process_slug, status, last run, next run, watermark

# GET /api/runs/{workflow_id}?page=1&page_size=20
# Returns paginated run history for one workflow

# GET /api/catalog
# Returns registered connectors (types + health) and destinations (types + schema version)
# and available analysis templates per destination

# GET /api/workflows/{workflow_id}/graph
# Returns Workflow IR shaped for React Flow:
# { nodes: [{id, type, data, position}], edges: [{id, source, target, animated, label}] }
# Position is placeholder (0,0) — dagre lays it out on the frontend

# GET /api/replays?workflow_id=...
# Returns replay_results rows from DuckDB (Sprint 4 — stub 404 for now)
```

Shape of `/api/workflows/{id}/graph` response:

```json
{
  "nodes": [
    { "id": "fetch_traces", "type": "connector",    "data": { "label": "Fetch Traces", "step": "fetch_traces", "status": "idle" }, "position": { "x": 0, "y": 0 } },
    { "id": "write_traces", "type": "destination",  "data": { "label": "Write Traces", "step": "write_traces", "status": "idle" }, "position": { "x": 0, "y": 0 } },
    { "id": "refresh_retailer_mart", "type": "transform", "data": { "label": "Retailer Mart", "step": "refresh_retailer_mart", "status": "idle" }, "position": { "x": 0, "y": 0 } }
  ],
  "edges": [
    { "id": "e1", "source": "fetch_traces", "target": "write_traces", "animated": false },
    { "id": "e2", "source": "write_traces", "target": "refresh_retailer_mart", "animated": false }
  ]
}
```

Node `status` values: `idle | running | succeeded | failed | skipped`. Updated live via SSE `run.step` events.

---

## apps/web structure

```
apps/web/
  biome.json
  tsconfig.json
  vite.config.ts
  package.json
  src/
    main.tsx
    App.tsx
    api/
      client.ts           # typed fetch wrappers for all REST endpoints
      sse.ts              # SSE hook: useSSE(url) → event stream
    store/
      processStore.ts     # Zustand store: processes list + live status patches
      dagStore.ts         # per-workflow node status map (step → status)
    pages/
      ProcessesPage.tsx   # table + status badges
      RunsPage.tsx        # run history per process
      CatalogPage.tsx     # connectors / destinations / templates
      DagPage.tsx         # React Flow canvas wrapper
    components/
      dag/
        NavbeFlow.tsx      # ReactFlow wrapper, loads graph + applies live overlay
        ConnectorNode.tsx  # custom node: blue, icon, metrics tooltip
        TransformNode.tsx  # custom node: amber
        DestinationNode.tsx # green
        ControlNode.tsx    # gray — branch / join / map
        NodeSidePanel.tsx  # step config + last run metrics (slide-in)
      StatusBadge.tsx
      RunMetrics.tsx
```

---

## Key implementation details

### vite.config.ts — proxy to daemon

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:7700",
      "/events": "http://127.0.0.1:7700",
    },
  },
})
```

### api/sse.ts — SSE hook

```ts
import { useEffect, useRef } from "react"

export function useSSE(url: string, onEvent: (e: MessageEvent) => void) {
  const ref = useRef<EventSource | null>(null)
  useEffect(() => {
    const es = new EventSource(url)
    ref.current = es
    es.onmessage = onEvent
    return () => es.close()
  }, [url])
}
```

### store/dagStore.ts — live node status

```ts
import { create } from "zustand"

type NodeStatus = "idle" | "running" | "succeeded" | "failed" | "skipped"

interface DagStore {
  nodeStatus: Record<string, Record<string, NodeStatus>> // workflowId → stepName → status
  patchStep: (workflowId: string, step: string, status: NodeStatus) => void
  resetRun: (workflowId: string) => void
}

export const useDagStore = create<DagStore>((set) => ({
  nodeStatus: {},
  patchStep: (wfId, step, status) =>
    set((s) => ({
      nodeStatus: { ...s.nodeStatus, [wfId]: { ...s.nodeStatus[wfId], [step]: status } },
    })),
  resetRun: (wfId) =>
    set((s) => ({ nodeStatus: { ...s.nodeStatus, [wfId]: {} } })),
}))
```

### components/dag/NavbeFlow.tsx

```tsx
import ReactFlow, { Background, Controls, MiniMap, useNodesState, useEdgesState } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import dagre from "@dagrejs/dagre"
import { useEffect } from "react"
import { useDagStore } from "../../store/dagStore"
import ConnectorNode from "./ConnectorNode"
import TransformNode from "./TransformNode"
import DestinationNode from "./DestinationNode"
import ControlNode from "./ControlNode"

const NODE_TYPES = { connector: ConnectorNode, transform: TransformNode,
                     destination: DestinationNode, control: ControlNode }

function layoutGraph(nodes, edges) {
  // dagre auto-layout: top-bottom, 180px node height
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 60 })
  nodes.forEach((n) => g.setNode(n.id, { width: 200, height: 60 }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map((n) => {
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - 100, y: pos.y - 30 } }
  })
}

export default function NavbeFlow({ workflowId }: { workflowId: string }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const nodeStatus = useDagStore((s) => s.nodeStatus[workflowId] ?? {})

  useEffect(() => {
    fetch(`/api/workflows/${workflowId}/graph`)
      .then((r) => r.json())
      .then(({ nodes: raw, edges: rawEdges }) => {
        setNodes(layoutGraph(raw, rawEdges))
        setEdges(rawEdges)
      })
  }, [workflowId])

  // Overlay live status onto node data
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        data: { ...n.data, status: nodeStatus[n.id] ?? "idle" },
      }))
    )
  }, [nodeStatus])

  return (
    <div style={{ height: 600 }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={NODE_TYPES}
                 onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                 fitView>
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  )
}
```

### Custom node pattern (ConnectorNode.tsx)

```tsx
import { Handle, Position } from "@xyflow/react"

const STATUS_COLORS = {
  idle: "#94a3b8",
  running: "#3b82f6",
  succeeded: "#22c55e",
  failed: "#ef4444",
  skipped: "#d1d5db",
}

export default function ConnectorNode({ data }) {
  const color = STATUS_COLORS[data.status ?? "idle"]
  return (
    <div style={{ border: `2px solid ${color}`, borderRadius: 8, padding: "8px 16px",
                  background: "#eff6ff", minWidth: 160, textAlign: "center",
                  boxShadow: data.status === "running" ? `0 0 12px ${color}` : "none",
                  transition: "box-shadow 0.4s" }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ fontWeight: 600, fontSize: 13 }}>{data.label}</div>
      <div style={{ fontSize: 11, color }}>{data.status}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}
```

Apply same pattern for Transform (amber `#fffbeb`), Destination (green `#f0fdf4`), Control (gray `#f8fafc`).

### SSE → dagStore wiring (App.tsx or DagPage.tsx)

```tsx
const { patchStep, resetRun } = useDagStore()

useSSE("/events/sse", (e) => {
  const event = JSON.parse(e.data)
  if (event.type === "run.started") resetRun(event.workflow_id)
  if (event.type === "run.step")
    patchStep(event.workflow_id, event.step, "succeeded")
  if (event.type === "run.step.started")
    patchStep(event.workflow_id, event.step, "running")
  if (event.type === "run.failed")
    patchStep(event.workflow_id, event.step, "failed")
})
```

---

## pnpm dependencies to add

```
@xyflow/react          # React Flow v12
@dagrejs/dagre         # auto-layout
zustand                # state management
```

---

## Vitest coverage

```ts
// src/store/dagStore.test.ts
import { useDagStore } from "./dagStore"

test("patchStep sets status for a step", () => {
  useDagStore.getState().patchStep("wf1", "fetch_traces", "running")
  expect(useDagStore.getState().nodeStatus["wf1"]["fetch_traces"]).toBe("running")
})

test("resetRun clears all step statuses for workflow", () => {
  useDagStore.getState().patchStep("wf1", "fetch_traces", "succeeded")
  useDagStore.getState().resetRun("wf1")
  expect(useDagStore.getState().nodeStatus["wf1"]).toEqual({})
})
```

---

## Done when

1. `pnpm dev` in `apps/web` opens UI at localhost:5173.
2. Processes page shows `langfuse_daily` with live status badge (SSE-driven).
3. DAG canvas renders the three-node langfuse graph; running a workflow turns nodes green in sequence.
4. Catalog page lists `langfuse` connector + `duckdb` destination + retailer template.
5. `pnpm check` passes (TS + Biome).
