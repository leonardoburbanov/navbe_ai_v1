# Sprint 8 — Runs-first cockpit: per-run DAG sheet, pause/stop, Settings hub

Reorient the Control UI around **runs as the primary object**. A process is a **filter** on runs, not a separate destination. Clicking a run opens a **left sheet** with that run’s live DAG and the report / experiment payload for the run. Add **pause** and **stop**. Collapse nav: drop Replays; fold Integrations into Settings with credentials next to each connector/destination.

**User pain:** *“I want to see the DAG per run, pause/stop it, browse runs first (process as filter), and manage auth where integrations live — not scatter Replays / Integrations / Settings.”*

---

## Defaults (locked)

| Knob | Choice | Why |
| --- | --- | --- |
| Primary page | **Runs** (default `?page=runs`) | Process = filter, not a separate home |
| Run detail | **Left sheet** (drawer from the left) | DAG + report without leaving the table |
| DAG scope | **Per `run_id`** (node states from that run’s events / stored steps) | Matches “dag per run” |
| Pause | Soft pause — skip starting the next LangGraph step; keep checkpoint | Laptop-safe; no thread kill |
| Stop | Cancel run — mark `cancelled`, refuse further steps, publish `run.cancelled` | Clear terminal state |
| Replays menu | **Remove** from nav; surface replay rows inside the run sheet / Reports | Less chrome |
| Integrations | **Merge into Settings** | Auth lives next to the integration card |

**Out of scope:** Visual IR editing, Temporal-style workflows, OS tray, multi-tenant auth UI.

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| DAG is workflow-scoped, not run-scoped | `DagPage` / `dagStore` keyed by `workflow_id` only |
| “Processes” feels like the product | Nav leads with Processes; Runs is secondary |
| No pause / stop | No cancel flag on `WorkflowRunModel`; `run_now` / `_execute` have no interrupt |
| Replays is a 4th nav island | Separate page; experiment report belongs with the run |
| Integrations ≠ Settings | Catalog vs Settings split; credentials only via MCP |
| Report not next to DAG | Reports / Replays pages are detached from the run row |

---

## Goal

With `navbe daemon` + `pnpm dev`:

1. Default landing is **Runs** with a process filter (All / `langfuse_daily` / …).
2. Click a run → **left sheet**: live/historical DAG for that `run_id` + report/experiment panel.
3. Running row shows **Pause** / **Stop**; paused can **Resume**; stopped is terminal.
4. Nav: `Runs` · `Reports` · `Settings` (no Replays, no separate Integrations, no standalone DAG/Processes pages — or keep Processes as a thin “schedules” subsection inside Settings).
5. Settings shows connectors + destinations with **auth / config** forms (redacted secrets) and email/Resend in the same place.
6. MCP `live_url` points at `?page=runs&workflow=…&run=…` (sheet opens on load).

---

## Information architecture

```text
Before                          After
------                          -----
Processes                       Runs  ← home (process filter)
Runs                            └─ left sheet: DAG + report
DAG                             Reports (templates / mart queries)
Replays                         Settings
Integrations (Catalog)            ├─ Connectors (+ auth)
Settings                          ├─ Destinations (+ paths)
                                  └─ Email / Resend
```

Replay experiment results: when a run’s output contains `compare_result` / `replay_id`, the run sheet **Report** tab shows the experiment report (reuse Sprint 6/7 Replays UI pieces). No top-level Replays nav.

---

## 1. Runs-first page + process filter

### Files

- Rewrite focus: [`apps/web/src/pages/RunsPage.tsx`](apps/web/src/pages/RunsPage.tsx)
- [`apps/web/src/App.tsx`](apps/web/src/App.tsx) — default `page=runs`; slim nav
- [`apps/web/src/components/ProcessSelector.tsx`](apps/web/src/components/ProcessSelector.tsx) — becomes “Filter by process” on Runs (All + slugs)
- Deprecate as top-level pages: `ProcessesPage`, `DagPage`, `ReplaysPage`, `CatalogPage` (fold logic elsewhere; delete nav entries)

### Behavior

- Table columns: process, run id (short), status, started, completed, latency/metrics snippet, actions.
- Filter: process dropdown (empty = all workflows with `process_slug`, plus optional “unnamed”).
- Live strip (Sprint 7) stays; clicking a live chip opens Runs with that `run` selected / sheet open.
- URL: `?page=runs&workflow=<id>&run=<run_id>` — if `run` set, open sheet on mount.

### API

Reuse `GET /api/runs/{workflow_id}`. Add:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/runs?process_slug=&page=&page_size=` | Cross-process run list for “All” filter |

---

## 2. Left sheet — DAG + report per run

### Files

- New: `apps/web/src/components/RunDetailSheet.tsx`
- Reuse: `NavbeFlow`, experiment report blocks from `ReplaysPage`, `RunMetrics`
- `dagStore`: key node status by **`run_id`** (or `workflow_id:run_id`); SSE `patchStep` uses `run_id` when present

### Sheet layout (left drawer, ~480–560px or 40vw)

```text
┌─────────────────────────────┐
│ Run · langfuse_daily · LIVE │  Pause  Stop  ✕
├─────────────────────────────┤
│ [DAG]  [Report]             │  tabs
│                             │
│  React Flow (read-only)     │  or experiment / mart preview
│  node colors for this run   │
└─────────────────────────────┘
```

| Tab | Content |
| --- | --- |
| **DAG** | Graph for the workflow IR; overlay step states for **this** `run_id` (live via SSE or reconstructed from run events / `output` if finished) |
| **Report** | If sync run: link/summary to mart refresh + optional template preview. If replay: experiment message diffs + field table. If email report: HTML path / send status from `output` |

### Historical DAG

For completed runs without live SSE: either

1. **ponytail:** paint all steps `succeeded`/`failed` from terminal status + last step in `output`, or  
2. Store `steps: [{id, status}]` on run complete (small additive JSON in `output`) — prefer (2) if cheap in `_execute`.

---

## 3. Pause and stop

### Control plane

Add to `WorkflowRunModel` (additive migration):

| Column | Type | Meaning |
| --- | --- | --- |
| `control` | `VARCHAR` nullable | `null` \| `pause_requested` \| `paused` \| `cancel_requested` \| `cancelled` |

Or a single `control_status` enum string. Keep `status` as `running` \| `completed` \| `failed` \| **`cancelled`** \| **`paused`**.

### Runtime (`agent._execute` / `run_now`)

Between LangGraph steps (same place as `run.step.started`):

```python
# ponytail: cooperative cancel between steps — not mid-httpx kill
ctrl = repo.get_run_control(run_id)
if ctrl == "cancel_requested":
    repo.fail_or_cancel(run_id, "cancelled")
    events.publish(..., "run.cancelled", ...)
    return partial_state
if ctrl == "pause_requested":
    repo.set_run_status(run_id, "paused")
    events.publish(..., "run.paused", ...)
    wait until resume or cancel  # or return and resume via run_now(resume=True)
```

**Pause v1 (simplest that works):** on `pause_requested`, finish current step, set status `paused`, exit `_execute` without failing. **Resume** = `POST /api/runs/{run_id}/resume` continues graph from checkpoint / or re-invokes remaining nodes from IR + last watermark (document limitation: if no LangGraph checkpoint persistence for mid-graph, pause only between top-level IR nodes and resume by re-entering `_execute` with `skip_completed_steps` list stored on run).

**ponytail ceiling:** no true mid-`httpx` abort this sprint; stop waits for current step to finish then cancels. Comment: `ponytail: cooperative cancel between steps → astream_events cancel if needed`.

### API + MCP

| Surface | Action |
| --- | --- |
| `POST /api/runs/{run_id}/pause` | Set `pause_requested` |
| `POST /api/runs/{run_id}/resume` | Clear pause; continue |
| `POST /api/runs/{run_id}/stop` | Set `cancel_requested` → `cancelled` |
| MCP `pause_run` / `resume_run` / `stop_run` | Same, return `live_url` |

### SSE

| Event | UI |
| --- | --- |
| `run.paused` | Badge paused; strip shows Paused |
| `run.cancelled` | Terminal; strip settles |
| existing succeed/fail | unchanged |

### UI

Sheet header + Runs row actions: Pause / Resume / Stop only when `status === running` or `paused`.

---

## 4. Remove Replays from nav; keep capability

### Behavior

- Delete nav item `replays`.
- Move experiment report UI into **Run sheet → Report** when `output.compare_result` or `replay_id` present.
- Optional: Reports page lists recent replay runs filtered by process `replay_*` — not required if sheet covers it.
- Keep `GET /api/replays` for sheet data fetch by `trace_id` / `replay_id` from run output.
- Update `live_url` for replay tools to `?page=runs&workflow=…&run=…`.

---

## 5. Settings = Integrations + auth + email

### Files

- Expand [`apps/web/src/pages/SettingsPage.tsx`](apps/web/src/pages/SettingsPage.tsx)
- Reuse catalog cards / drawers from `apps/web/src/components/catalog/*`
- Remove Catalog from top nav (`Integrations` label goes away)

### Sections (one page, scroll or sub-tabs)

1. **Connectors** — list Langfuse connections; expand/edit host + rotate keys (write via thin REST wrapping existing MCP `create_connector` / update if exists; redact secrets).
2. **Destinations** — DuckDB/SQLite path, schema version; switch path with confirm.
3. **Email** — existing Resend / SMTP + report preview/schedule (already on Settings).
4. **Schedules** (optional thin) — list process slugs + cron + next run (replaces orphaned Processes page).

### API (thin REST, demo user)

Prefer wrapping existing MCP tools:

- `GET /api/catalog` (already)
- `POST /api/connectors` / patch secrets (if missing, add minimal update endpoint)
- Never return raw secret keys — show `••••` + “Replace key” field

---

## 6. MCP / deep link updates

| Change | Detail |
| --- | --- |
| `live_process_url` default page | `runs` not `dag` |
| Query | `?page=runs&workflow=&run=` opens sheet |
| New tools | `pause_run`, `resume_run`, `stop_run` |
| `run_workflow` response | Still `live_url`; mention Pause/Stop in UI |

---

## Implementation order

1. Nav IA: Runs home; remove Replays / Integrations / DAG / Processes from top nav; Settings absorbs catalog.
2. `GET /api/runs` cross-process list + Runs filter UX.
3. `RunDetailSheet` left drawer with DAG tab (workflow IR + run-scoped status).
4. Report tab (metrics + experiment report reuse).
5. Run control columns + pause/stop/resume API + cooperative cancel in `_execute`.
6. MCP tools + `live_url` page=`runs`.
7. Settings integrations + auth forms.
8. Smoke: run langfuse_daily → open live_url → sheet DAG live → Pause → Resume → Stop on a long run.

---

## Done signal

1. Default UI opens **Runs**; process filter works; click run opens **left sheet** with DAG.
2. Report tab shows sync metrics or replay experiment diffs for that run.
3. Pause / Stop / Resume work on a running graph (cooperative between steps); SSE + badges update.
4. No Replays or Integrations top-level nav; Settings hosts connectors/destinations/auth/email.
5. MCP `live_url` opens Runs with the sheet for that run.
6. `pnpm check` / ruff clean on touched files.

---

## Non-goals

- Killing in-flight HTTP mid-request.
- Full LangGraph checkpoint resume across daemon restarts (document if pause state is lost on restart).
- Creating connectors with full MCP elicitation UX parity (Settings can be “edit + validate”; create may still hint MCP).
- Desktop shell / tray.
