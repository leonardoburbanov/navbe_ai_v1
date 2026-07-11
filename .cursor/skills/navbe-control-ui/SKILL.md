---
name: navbe-control-ui
description: Implements Sprint 3 of Navbe — the Vite+React+TypeScript Control UI with Processes, Runs, Catalog, and DAG canvas pages. The DAG canvas uses @xyflow/react with dagre auto-layout and live SSE-driven node state coloring. Use when building or modifying any part of apps/web, the React Flow DAG, the Zustand dagStore, or the navbe_api graph endpoint.
---

# Navbe Control UI — Sprint 3

Full spec: [.cursor/plans/sprint3-control-ui.md](.cursor/plans/sprint3-control-ui.md)

## Stack

- Vite 6 + React 19 + TypeScript strict
- `@xyflow/react` (React Flow v12) for the DAG canvas
- `@dagrejs/dagre` for auto-layout (top-to-bottom, no manual positions)
- `zustand` for client state (`processStore`, `dagStore`)
- Biome for lint + format (`pnpm biome check --write src/`)
- Vitest for pure logic tests

## Daemon endpoints consumed

| Endpoint | Page |
| --- | --- |
| `GET /api/processes` | ProcessesPage |
| `GET /api/runs/{workflow_id}` | RunsPage |
| `GET /api/catalog` | CatalogPage |
| `GET /api/workflows/{id}/graph` | DagPage |
| `GET /api/replays` | ReplaysPage (Sprint 4) |
| `GET /events/sse` | All pages (live status) |

All calls go through `src/api/client.ts` — typed fetch wrappers only, no raw `fetch` elsewhere.

## DAG canvas rules

- **Custom node types only** — no default React Flow node. Each type (`connector`, `transform`, `destination`, `control`) has its own component.
- **Status drives visual state** — border color + box-shadow glow for `running`. No custom CSS classes. Use inline `style` so the status color map is the single source of truth.
- **dagre layout on every graph load** — call `layoutGraph(nodes, edges)` after fetching IR. Positions come from dagre, not the server.
- **SSE → dagStore → node data** — the only path to update node status. Never mutate React Flow node state directly.
- **Read-only** — no drag, no connect, no delete in this sprint. Disable `nodesDraggable` and `nodesConnectable` on `<ReactFlow>`.

## Status color map

```ts
const STATUS_COLORS = {
  idle:      "#94a3b8",   // slate-400
  running:   "#3b82f6",   // blue-500  (+ glow)
  succeeded: "#22c55e",   // green-500
  failed:    "#ef4444",   // red-500
  skipped:   "#d1d5db",   // gray-300
} as const
```

## SSE event → dagStore mapping

| Event `type` | Action |
| --- | --- |
| `run.started` | `resetRun(workflow_id)` — clear all node statuses |
| `run.step.started` | `patchStep(workflow_id, step, "running")` |
| `run.step` | `patchStep(workflow_id, step, "succeeded")` |
| `run.failed` | `patchStep(workflow_id, step, "failed")` |

Wire in the top-level SSE listener; do not duplicate in individual page components.

## Vitest tests required

- `dagStore.test.ts`: patchStep, resetRun
- `statusBadge.test.ts`: correct badge text/color for each status value
- `sse.test.ts`: SSE event → correct dagStore action

## vite.config.ts proxy

```ts
server: { proxy: { "/api": "http://127.0.0.1:7700", "/events": "http://127.0.0.1:7700" } }
```

## Done signal

1. `pnpm dev` opens UI at localhost:5173.
2. Processes page shows `langfuse_daily` with live status badge.
3. Click process → DAG canvas renders 3-node graph; running a workflow turns nodes green in sequence.
4. `pnpm check` exits 0 (TS + Biome).
5. `pnpm test` passes (dagStore + statusBadge + SSE unit tests).
