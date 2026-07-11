# Sprint 7 — Live process cockpit + MCP deep links

When an agent starts a run (MCP `run_workflow`, scheduled tick, replay, report), the human cockpit must **proactively** show that process as live — without the user refreshing. MCP tool responses return a **clickable Control UI URL** so the agent can open the live view in the same breath.

**User pain:** *“If I run a process, I want to see it running in the frontend — and MCP should give me the URL to watch it live.”*

---

## Defaults (locked)

| Knob | Choice | Why |
| --- | --- | --- |
| Push channel | **SSE** (existing `/events/sse`) | Already on the bus; laptop-safe; no WebSocket/NATS |
| Poll fallback | Processes list refresh on focus + 5s while any run is `running` | Recover if SSE drops |
| Live landing page | **DAG** (`?page=dag&workflow=<id>&run=<run_id>`) | Graph is the “watching” surface; Processes badge for list |
| UI base URL | `NAVBE_UI_URL` (default `http://127.0.0.1:5173`) | MCP returns absolute links |
| Toast / banner | In-app live strip (not OS toasts this sprint) | Same bus; tray later |

**Out of scope:** Tauri tray toasts, multi-machine fan-out, WebSocket, replacing SSE with polling-only.

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| Run starts but UI looks idle until refresh | SSE updates DAG steps + process status patchily; Processes table does not auto-refetch on `run.started` |
| Agent has no link to share | MCP tools return `next_step` text only — no `live_url` |
| Deep link incomplete | URL has `page` + `workflow`; no `run=` / auto-open live strip |
| Replay / one-shot via `_run_tool` outside daemon | Events may skip bus if `events.init` missing — daemon path is fine; keep publish on `run_now` / `_on_fire` |
| Step “running” flicker | `run.step.started` exists; ensure all graph runners emit it before each step |

---

## Goal

With `navbe daemon` + `pnpm dev`:

1. Agent calls `run_workflow` (or schedule fires) → MCP response includes `live_url`.
2. Opening that URL shows the DAG with nodes coloring live (pending → running → succeeded/failed).
3. Processes page shows a **Live** badge / pulse without manual refresh.
4. A persistent **Live runs** strip lists in-flight runs; click jumps to that DAG.
5. On `run.succeeded` / `run.failed`, strip updates and badge settles — no full page reload required.

---

## Architecture

```text
 run_now / _on_fire / replay save
        │
        ▼ publish(run.started | run.step.started | run.step | run.succeeded | run.failed)
 ┌──────────────────┐
 │ Event bus SQLite │
 └────────┬─────────┘
          │ fan-out
          ▼
   GET /events/sse  ──► Control UI (EventSource)
                          ├─ processStore.patchStatus
                          ├─ dagStore.resetRun / patchStep
                          └─ liveRunStore.upsert / remove

 MCP tool response:
   { run_id, status, live_url: "http://127.0.0.1:5173/?page=dag&workflow=…&run=…" }
```

**ponytail:** one SSE pipe already exists — extend client stores; do not add a second push protocol.

---

## 1. Config — UI base URL

### Files

- [`packages/navbe_core/navbe_core/config.py`](packages/navbe_core/navbe_core/config.py)
- Thin helper: `packages/navbe_core/navbe_core/live_url.py` (or function on Settings)

### Behavior

```python
# Settings
UI_URL: str = "http://127.0.0.1:5173"  # env NAVBE_UI_URL

def live_process_url(*, workflow_id: str, run_id: str | None = None, page: str = "dag") -> str:
    """Absolute Control UI deep link for a live (or just-started) run."""
    q = f"page={page}&workflow={workflow_id}"
    if run_id:
        q += f"&run={run_id}"
    return f"{settings.UI_URL.rstrip('/')}/?{q}"
```

---

## 2. MCP — return `live_url` on every run start

### Tools to update (same shape)

| Tool | When |
| --- | --- |
| `run_workflow` | Always on success |
| `preview_workflow` | Use `page=dag` + note preview (or `page=runs`) |
| `replay_trace_to_api` | When `save_as_workflow` or always with destination — link to Replays **and** DAG if workflow_id set |
| `send_daily_report` / scheduled `_on_fire` path via `get_process_status` | Include `live_url` for latest run |

### Response shape (additive)

```json
{
  "run_id": "...",
  "workflow_id": "...",
  "process_slug": "langfuse_daily",
  "status": "running",
  "live_url": "http://127.0.0.1:5173/?page=dag&workflow=…&run=…",
  "next_step": "Open live_url in the browser to watch the DAG; or pull_events"
}
```

`get_process_status` when status is `running` / last run running: also return `live_url`.

---

## 3. Daemon events — consistent live payloads

### Files

- [`packages/navbe_core/navbe_core/agent.py`](packages/navbe_core/navbe_core/agent.py) — `run_now`, `_on_fire`, `_execute`

### Behavior

Every publish for UI must include:

```json
{
  "workflow_id": "...",
  "run_id": "...",
  "process_slug": "...",
  "status": "running|completed|failed",
  "step": "fetch_traces"  
}
```

Ensure:

1. `run.started` **before** first step (already).
2. `run.step.started` **before** each node (already in `_execute`).
3. `run.step` / `run.failed` after.
4. `run.succeeded` / `run.failed` terminal with `run_id`.

Replay / report paths that bypass `_execute` must either use `run_now` or publish the same events (otherwise Live strip stays empty). Prefer routing “save_as_workflow + record run” through a small `publish_run_lifecycle` helper so one place owns the event shape.

---

## 4. Control UI — live stores + strip

### Files

- New: `apps/web/src/store/liveRunStore.ts` — in-flight runs by `run_id`
- [`apps/web/src/api/sse.ts`](apps/web/src/api/sse.ts) — map SSE → `liveRunStore` + existing dag/process stores
- New: `apps/web/src/components/LiveRunsStrip.tsx`
- [`apps/web/src/App.tsx`](apps/web/src/App.tsx) — mount strip under header; parse `run` query param
- [`apps/web/src/pages/ProcessesPage.tsx`](apps/web/src/pages/ProcessesPage.tsx) — pulse badge from `liveRunStore` / processStore
- [`apps/web/src/pages/DagPage.tsx`](apps/web/src/pages/DagPage.tsx) / `NavbeFlow` — highlight active run; “LIVE” chip when strip has this workflow

### SSE mapping (extend `handleSsePayload`)

| Event | Action |
| --- | --- |
| `run.started` / `run.preview.started` | `liveRunStore.upsert`; `processStore.patchStatus(running)`; `dagStore.resetRun` |
| `run.step.started` | `dagStore.patchStep(running)` |
| `run.step` | `dagStore.patchStep(succeeded)` |
| `run.succeeded` / `run.preview.completed` | `liveRunStore.complete`; process → completed |
| `run.failed` | `liveRunStore.fail`; process → failed |

### LiveRunsStrip UX

- Fixed under nav: “Live: langfuse_daily · fetch_traces · 12s” (pulse).
- Click → `setPage('dag')` + set workflow/run in URL.
- Empty → hide strip (no clutter).
- Max ~5 rows; older completed drop after 30s or on dismiss.

### URL

```
?page=dag&workflow=<workflow_id>&run=<run_id>
```

On load: select process, open DAG, keep SSE driving node colors. If run already finished, show last status (fetch run once optional).

### Processes page

- Row status badge: if `liveRunStore` has workflow → **running** with CSS pulse (even before refetch).
- Optional: soft refetch `GET /api/processes` when any live run starts/ends.

---

## 5. Optional thin REST (same sprint if useful)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/runs/live` | List in-flight runs from control plane (`status=running`) for strip hydrate on page load |

Hydrate `liveRunStore` on mount so a late-opening browser still sees active runs (SSE alone misses past `run.started`).

---

## 6. Agent UX copy

When Cursor/Hermes runs a workflow, the tool result should be enough for the agent to say:

> Process `langfuse_daily` is running. Watch it live:  
> http://127.0.0.1:5173/?page=dag&workflow=53d8…&run=a25a…

No separate “open browser” MCP tool this sprint — URL in the response is the contract.

---

## Implementation order

1. `NAVBE_UI_URL` + `live_process_url()` helper.
2. Add `live_url` to `run_workflow` / `get_process_status` / replay save responses.
3. `liveRunStore` + SSE mapping + `LiveRunsStrip`.
4. URL `run=` param + Processes pulse badge.
5. `GET /api/runs/live` hydrate.
6. Smoke: MCP `run_workflow` → paste `live_url` → DAG nodes turn blue then green.

---

## Done signal

1. `run_workflow` JSON includes `live_url` pointing at Control UI with `page=dag&workflow=&run=`.
2. With UI open on Processes, starting a run via MCP shows **Live** strip + pulse without refresh.
3. Opening `live_url` in a cold tab connects SSE and shows step progress on the DAG.
4. Terminal `run.succeeded` / `run.failed` clears or settles the strip.
5. `pnpm check` / ruff clean on touched files.
6. No new push dependency (SSE only).

---

## Non-goals

- Desktop tray / OS notifications (Phase 4 / desktop shell).
- Agent-initiated `window.open` automation.
- Per-step log streaming (metrics/events enough; full log pane later).
- Changing Workflow IR.
