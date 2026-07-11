# Sprint 6 — Control UI cockpit: see DAGs, runs, connectors

Make the human cockpit usable without MCP literacy. Today Processes/Runs/DAG/Catalog often look empty or unreachable because of silent API failures, disabled nav, and a flat Catalog that does not feel like “integrations.”

**User pain:** *“I can’t see the DAGs, runs, connectors, integrations…”*

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| Empty Processes | `ProcessesPage` swallows fetch errors → “No named processes yet” even when daemon is down |
| Runs / DAG greyed out | Top nav `disabled={!workflowId}` — must click row buttons first; no process picker |
| No “integrations” | Only flat Catalog list; no Connections / Destinations detail pages |
| DAG never “running” | UI listens for `run.step.started`; daemon only emits `run.step` on success |
| Lost context on refresh | No URL/`?workflow=` persistence |
| Email / Resend invisible | MCP-only (`configure_resend`, `preview_daily_report`) — no Settings UI |

Pages that exist: Processes, Runs, Catalog, Reports, DAG, Replays (`apps/web/src/App.tsx`).

Daemon Control UI routes already match the client for those pages — **no path mismatch**. Gap is UX + coverage, plus a few thin REST wrappers for settings.

---

## Goal

With `navbe daemon` + `pnpm dev`:

1. Health bar shows daemon online/offline.
2. `langfuse_daily` appears on Processes (or clear setup empty-state).
3. Header process selector unlocks Runs + DAG without hunting row buttons.
4. Catalog shows connectors / destinations / templates as cards with detail drawers.
5. DAG loads with loading/empty states; live step coloring works with existing `run.step` events.
6. Runs show history with expandable metrics.
7. Settings page configures Resend and previews/schedules the daily email report.

---

## 1. Shell: health + process context

### Files

- [`apps/web/src/App.tsx`](apps/web/src/App.tsx)
- [`apps/web/src/api/client.ts`](apps/web/src/api/client.ts) — add `fetchHealth()`
- New: `apps/web/src/components/HealthBar.tsx`
- New: `apps/web/src/components/ProcessSelector.tsx`

### Behavior

- Poll `GET /health` every 5s (or on focus). Offline → banner: “Start `uv run navbe daemon` on :7700”.
- SSE connection indicator (connected / reconnecting) from existing `useSSE`.
- **Process selector** in header: options from `GET /api/processes`. Selecting sets `workflowId` + `processSlug` and enables Runs/DAG.
- Persist selection: `?workflow=<id>&page=<page>` via `URLSearchParams` (no full router required).
- Runs/DAG nav: never permanently disabled — if no process selected, open selector / Processes with hint.

---

## 2. Processes: errors + empty states

### File

- [`apps/web/src/pages/ProcessesPage.tsx`](apps/web/src/pages/ProcessesPage.tsx)

### Behavior

- Surface fetch errors (retry button) — stop silent `catch → []`.
- Empty states:
  - **Offline** — link to health message.
  - **Online, zero processes** — copy: create via MCP `create_langfuse_export_workflow` with `process_slug=langfuse_daily`.
- Keep row actions: DAG / Runs / Results.

### Optional thin API (same sprint if needed)

- `GET /api/workflows` Control UI twin (demo user, no API key) listing **all** workflows, including those without `process_slug`, so nothing is invisible. Prefer showing slug-less as “unnamed” rather than hiding.

---

## 3. Catalog v2 — connectors & destinations as integrations

### Files

- [`apps/web/src/pages/CatalogPage.tsx`](apps/web/src/pages/CatalogPage.tsx)
- New: `apps/web/src/components/catalog/ConnectorCard.tsx`
- New: `apps/web/src/components/catalog/DestinationCard.tsx`
- New: `apps/web/src/components/catalog/DetailDrawer.tsx`

### Behavior

- Three sections as **cards**, not bare `<ul>`:
  - **Connectors** (Langfuse integrations) — name, host, status badge
  - **Destinations** — type, schema version, path/summary from catalog
  - **Analysis templates** — name + “Open in Reports”
- Click card → **detail drawer** (read-only): host, status, destination id, template `query_example`, “Open in Reports”.
- Empty catalog: explain MCP `create_connector` / `create_destination`.

### API

Reuse `GET /api/catalog`. Extend catalog payload if needed:

```json
{
  "destinations": [{
    "id": "...",
    "type": "duckdb",
    "name": "...",
    "schema_version": 1,
    "config_summary": { "db_path": "...", "table": "traces" },
    "templates": [{ "id": "...", "name": "...", "description": "...", "query_example": "..." }]
  }]
}
```

Redact secrets; never return keys. `config_summary` is path/type only.

**Out of scope:** create/edit credentials in UI (still MCP + `needs_input`).

---

## 4. DAG polish + live steps

### Files

- [`apps/web/src/components/dag/NavbeFlow.tsx`](apps/web/src/components/dag/NavbeFlow.tsx)
- [`apps/web/src/api/sse.ts`](apps/web/src/api/sse.ts)
- [`apps/web/src/pages/DagPage.tsx`](apps/web/src/pages/DagPage.tsx)
- Optional backend: [`packages/navbe_core/navbe_core/agent.py`](packages/navbe_core/navbe_core/agent.py) — emit `run.step.started` before each step (small additive event)

### Behavior

- Loading skeleton while graph fetches.
- Empty IR: “This workflow has no graph nodes.”
- Fix SSE mapping: treat `run.step` as **succeeded** (already) **and** on `run.started` reset; optionally mark next node running if `run.step.started` is added.
- Show process slug + workflow id in DagPage header.
- Ensure `build_retailer_report` / `send_email_report` / `refresh_retailer_mart` appear when opening `langfuse_daily` or `langfuse_daily_report` graphs.

---

## 5. Runs v2

### Files

- [`apps/web/src/pages/RunsPage.tsx`](apps/web/src/pages/RunsPage.tsx)
- [`apps/web/src/components/RunMetrics.tsx`](apps/web/src/components/RunMetrics.tsx) — wire if unused

### Behavior

- Table: status, started, completed, error snippet.
- Expand row → metrics from run `output` (trace_count, observation_count, mart_refreshed, email_sent, etc.).
- Pagination controls using existing `page` / `page_size`.
- Process selector context: if no `workflowId`, prompt to pick a process.

---

## 6. Settings — Email / Resend + report actions

### Files

- New: `apps/web/src/pages/SettingsPage.tsx`
- [`apps/web/src/api/client.ts`](apps/web/src/api/client.ts)
- Thin REST in [`packages/navbe_api/navbe_api/app.py`](packages/navbe_api/navbe_api/app.py) (demo user, no API key):

| Method | Path | Wraps |
| --- | --- | --- |
| `POST` | `/api/settings/resend` | `configure_resend` |
| `GET` | `/api/settings/email` | redacted status `{ provider, from_addr, configured }` |
| `POST` | `/api/reports/preview` | `preview_daily_report` |
| `POST` | `/api/reports/schedule` | `schedule_daily_report` |
| `POST` | `/api/reports/send` | `send_daily_report` |

### UI

- Form: Resend API key + from address (key never echoed back after save).
- Status: “Configured (resend)” / “Not configured”.
- Actions: Preview report (destination picker), Schedule (email_to + cron), Send now.
- Link from Reports page: “Email settings”.

---

## 7. Nav IA

Update header tabs order:

`Processes | Runs | DAG | Catalog | Reports | Replays | Settings`

Rename Catalog subtitle to **Integrations** in the page H2 (keep route key `catalog` to avoid churn).

---

## Out of scope

- Visual DAG editing / drag-connect
- Writing Langfuse credentials from the UI
- Desktop/Tauri shell
- Full schedule editor for arbitrary workflows
- Charts on Reports page

---

## Done signal

1. Kill daemon → HealthBar shows offline; start daemon → online.
2. With `langfuse_daily` in hub: Processes lists it; selector enables Runs + DAG; DAG renders 3+ nodes; Runs lists history.
3. Catalog cards show connector + DuckDB destination; drawer shows template SQL; Open in Reports works.
4. Run a workflow → DAG nodes turn green via SSE (and running state if `run.step.started` added).
5. Settings → save Resend (or show already configured) → Preview writes HTML path; Send/Schedule callable from UI.
6. `pnpm check` / `pnpm test` pass for touched web code.

---

## Implementation order

1. HealthBar + ProcessSelector + URL state + Processes errors  
2. Catalog cards + drawer + catalog payload `config_summary`  
3. DAG loading/empty + SSE fix (+ optional `run.step.started`)  
4. Runs expand metrics  
5. Settings + thin REST for Resend/report  

---

## Skill (optional same PR)

`.cursor/skills/navbe-control-ui-cockpit/SKILL.md` — point agents at HealthBar, ProcessSelector, Settings REST, and “never silent-catch list fetches.”
