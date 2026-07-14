# Sprint 9 — Workflows as first-class: rename, MCP CRUD, Workflows view

Collapse the dual **process / workflow** vocabulary into **workflow** everywhere (code + UX). Agents author and mutate Workflow IR via MCP in natural language (trigger, sources, destinations, steps, edges with intelligent wiring). Humans browse and inspect those workflows in a new Control UI **Workflows** page.

**User pain:** *“I want workflows — not ‘processes’ — I can create and edit through MCP, and see them in the UI.”*

---

## Defaults (locked)

| Knob | Choice | Why |
| --- | --- | --- |
| Product noun | **Workflow** (drop “process” in UI + new MCP names) | Matches IR + `WorkflowModel`; one word |
| Friendly id | Keep column `process_slug` → rename to **`slug`** (additive migrate) | Still the handle agents ask about (`langfuse_daily`) |
| Event topics | Dual-publish `workflow.{slug}` **and** `process.{slug}` this sprint | Don’t break Sprint 1–7 subscribers |
| MCP rename | New canonical tools; old names thin aliases one sprint | Agents mid-flight keep working |
| Authoring | `propose_workflow` → `confirm_workflow` + mutators | AGENTS.md already; today only `suggest` + `schedule` |
| Edge wiring | Registry rules (source→dest type compat), not LLM inventing edges | Deterministic, laptop-safe |
| UI | New top-nav **Workflows** page (list + detail DAG read-only) | Runs stay run-centric (Sprint 8); Workflows = definitions |
| Visual IR edit | **Out of scope** — MCP authors; UI reads | Canvas stays read-only |

**Out of scope:** Drag-drop IR editor, Temporal/Airflow clone, new connectors beyond wiring existing step registry, deleting event dual-publish (do in Sprint 10+).

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| “Process” vs “workflow” everywhere | `process_slug`, `list_processes`, `get_process_status`, `processStore`, `ProcessesPage` vs `WorkflowModel`, `list_workflows`, `run_workflow` |
| Can’t author a general graph via MCP | Only templates: `create_langfuse_export_workflow`, `schedule_daily_report`, `suggest_workflow` → `schedule_workflow` |
| No update / delete of IR pieces | No `update_workflow` / node mutators; context JSON is write-once at create |
| Edges are hand-copied from `SOURCES` | `sources.py` has static graphs; no “connect A→B if compatible” helper |
| No Workflows nav | Sprint 8 dropped Processes; definitions are invisible except as a Runs filter |

---

## Goal

With `navbe daemon` + `pnpm dev` + MCP:

1. UI says **Workflow** (nav, filters, labels, empty states) — no user-facing “process”.
2. Agent: `propose_workflow("monitor langfuse daily into duckdb")` → draft IR → `confirm_workflow` → appears on **Workflows** page with DAG.
3. Agent can add/replace trigger, bind source connector + destination, append/remove steps, and auto-wire edges via MCP mutators.
4. `list_workflows` / `get_workflow_status` are the canonical status tools; `list_processes` / `get_process_status` still work as aliases.
5. Runs page filter label: “Filter by workflow”; deep links unchanged (`?page=runs&workflow=`).

---

## Information architecture

```text
Sprint 8                            Sprint 9
--------                            --------
Runs (home, process filter)         Runs (home, workflow filter)
Reports                             Workflows  ← NEW (definitions + DAG)
Settings                            Reports
                                    Settings
```

**Runs** = instances. **Workflows** = durable IR + schedule + slug. Same `workflow_id` links both.

---

## 1. Rename: process → workflow (code + UX)

### Naming map

| Old | New (canonical) | Notes |
| --- | --- | --- |
| `process_slug` (column / JSON) | `slug` | DB: add `slug`, backfill from `process_slug`, keep old col readable one sprint |
| `list_processes` | `list_workflows` (extend existing) | Merge slug + schedule + last status into one tool |
| `get_process_status` | `get_workflow_status` | Accept `slug` or `workflow_id` |
| `process.{slug}` topic | `workflow.{slug}` | Dual-publish both |
| `processStore` | `workflowStore` | Rename file + hooks |
| `ProcessSelector` | `WorkflowSelector` | Label: “Filter by workflow” |
| `ProcessesPage` | delete / replace by `WorkflowsPage` | |
| UI copy “process” | “workflow” | Live strip, runs columns, Settings schedules |
| `live_process_url` | `live_workflow_url` | Alias old name |

### Files (high-touch)

- Core: [`packages/navbe_core/navbe_core/models.py`](packages/navbe_core/navbe_core/models.py), `repository.py`, `agent.py`, `live_url` helper
- MCP: `list_processes.py` → alias; extend `list.py`; new `get_workflow_status.py` (+ alias file)
- API: [`packages/navbe_api/navbe_api/app.py`](packages/navbe_api/navbe_api/app.py) — `/api/processes` → `/api/workflows` (keep old route redirect/alias)
- Web: `App.tsx`, `RunsPage`, `LiveRunsStrip`, `RunDetailSheet`, stores, selector, client types
- Docs: [`AGENTS.md`](AGENTS.md) glossary — Process = deprecated alias of workflow slug

### Migration rules

1. Additive only: `ALTER TABLE workflows ADD COLUMN slug` (or rename via copy+drop later).
2. API responses include **both** `slug` and `process_slug` (= same value) this sprint.
3. SSE payloads: prefer `slug`; still send `process_slug` for existing UI until web rename lands in same PR.
4. Do **not** rename `workflow_id` / `WorkflowModel` / `run_workflow`.

**ponytail:** one rename PR (or first half of sprint) — string + store renames; no behavior change yet.

---

## 2. Workflow IR contract (explicit, tiny)

Persist in `workflows.context` (existing JSON). Canonical shape:

```json
{
  "action": "graph",
  "graph": {
    "entry": "fetch_traces",
    "nodes": ["fetch_traces", "write_traces", "refresh_retailer_mart"],
    "edges": [["fetch_traces", "write_traces"], ["write_traces", "refresh_retailer_mart"]]
  },
  "input": {
    "connector_id": "...",
    "destination_id": "...",
    "limit": 50
  },
  "trigger": {
    "type": "cron",
    "cron": "0 6 * * *",
    "tz": "UTC",
    "overlap_policy": "run_once_catchup"
  }
}
```

| Piece | Meaning |
| --- | --- |
| `trigger` | `manual` \| `cron` \| `mcp_tool` — cron mirrors `WorkflowModel.cron_expression` (single source: model wins for scheduler; context mirrors for IR display) |
| `input.connector_id` / sources | Bound connection(s); MVP: one primary connector |
| `input.destination_id` | Bound destination |
| `graph.nodes` | Step ids registered in LangGraph step registry |
| `graph.edges` | Directed pairs; validated by `build_graph` |

Extend [`packages/navbe_api/navbe_api/graph.py`](packages/navbe_api/navbe_api/graph.py) to surface trigger + bound source/dest labels on the Workflows detail view (not only bare steps).

---

## 3. MCP — CRUD + NL mutators + intelligent edges

### 3a. Propose / confirm (create)

| Tool | Behavior |
| --- | --- |
| `propose_workflow` | NL intent → draft IR (reuse `SOURCES` + `match_source` + registry). **Does not persist.** Returns markdown + `draft` + `needs_input` if connector/destination missing. |
| `confirm_workflow` | Persist draft → `WorkflowModel` + optional schedule. Sets `slug` (from intent or explicit). Returns `workflow_id`, `slug`, `live_url` (Workflows page). |

Deprecate pure “suggest then schedule with opaque context” as the *primary* path; keep `suggest_workflow` as alias → `propose_workflow` for one sprint.

Template tools (`create_langfuse_export_workflow`, `schedule_daily_report`) remain shortcuts that call the same confirm path under the hood.

### 3b. Read / update / delete

| Tool | Behavior |
| --- | --- |
| `list_workflows` | All workflows: id, name, slug, status, cron, node count, last run summary |
| `get_workflow` / `recall_workflow` | Full IR + bindings (extend `recall_workflow`) |
| `get_workflow_status` | Live status (alias of today’s `get_process_status`) |
| `update_workflow` | Patch name, slug, task_description, enabled/paused |
| `delete_workflow` | Soft-delete or hard-delete if no running run; refuse if lock held |
| `set_workflow_trigger` | NL or structured cron/`manual`; updates model + context.trigger |
| `set_workflow_source` | Bind `connector_id` (validate type vs graph entry step) |
| `set_workflow_destination` | Bind `destination_id` |
| `add_workflow_step` | Append registered step id; **auto-wire** edges via connector rules |
| `remove_workflow_step` | Remove node + incident edges; recompute entry if needed |
| `connect_workflow_steps` | Explicit edge override when auto-wire is ambiguous |

**Natural language:** mutator tools accept either structured args **or** a short `hint` string parsed with the same alias tables as `SOURCES` / step registry (e.g. `add_workflow_step(workflow_id, hint="then refresh the retailer mart")` → `refresh_retailer_mart`).

### 3c. Intelligent connectors (edge rules)

New small module: `packages/navbe_core/navbe_core/wiring.py` (or extend `sources.py`).

```text
Rule table (examples):
  fetch_traces        → write_traces
  write_traces        → refresh_retailer_mart
  refresh_retailer_mart → build_retailer_report
  build_retailer_report → send_email_report
  fetch_trace         → call_api → compare_outputs → store_replay
```

On `add_workflow_step`:

1. Look up allowed predecessors / successors for the new step.
2. If exactly one existing node is a valid predecessor → add that edge.
3. If multiple → return `needs_input` with candidate edges (agent or `connect_workflow_steps`).
4. Never invent unknown step ids; only registered handlers.

**ponytail:** static adjacency dict keyed by step id — no ML. Ceiling → typed ports when a second connector family appears.

### 3d. Agent UX contract

Every mutator response includes:

- `workflow_id`, `slug`
- `graph` summary (nodes + edges)
- `next_step` hint
- `ui_url`: `http://127.0.0.1:5173/?page=workflows&workflow=<id>`

---

## 4. Control UI — Workflows view

### Nav

`Runs` · `Workflows` · `Reports` · `Settings`

### Page: `WorkflowsPage.tsx`

**List**

| Column | Source |
| --- | --- |
| Name / slug | workflow |
| Trigger | cron or Manual |
| Steps | node count or chip list |
| Source → Dest | connector name → destination name |
| Last run | status badge + relative time |
| Actions | Open detail, Run now, Open runs (filtered) |

Empty state: “Create via MCP `propose_workflow` / `confirm_workflow`” with example hint.

**Detail** (same page split or right panel — prefer **right panel** to mirror run sheet without fighting Sprint 8 left sheet)

- Read-only DAG (`NavbeFlow` / existing graph endpoint)
- Trigger + bindings card
- Buttons: Run now → deep-link Runs sheet; “View runs” filter

### API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/workflows` | List (canonical; `/api/processes` alias) |
| `GET /api/workflows/{id}` | Detail: IR + bindings + last run |
| `GET /api/workflows/{id}/graph` | Already exists |
| `POST /api/workflows/{id}/run` | Thin wrap `run_workflow` (optional if MCP-only run is enough) |

No IR PATCH from UI this sprint — MCP is the authoring surface.

### Files

- New: `apps/web/src/pages/WorkflowsPage.tsx`
- Rename: `processStore` → `workflowStore`, `ProcessSelector` → `WorkflowSelector`
- [`apps/web/src/App.tsx`](apps/web/src/App.tsx) — page type `workflows`
- [`apps/web/src/api/client.ts`](apps/web/src/api/client.ts) — typed clients
- Remove dead `ProcessesPage` nav usage (file can stay deleted or redirected)

---

## 5. AGENTS.md / glossary sync

Update working agreement + glossary:

- **Workflow** — durable IR + schedule + slug; what agents and UI name.
- **Process** — deprecated synonym of workflow slug; keep only in migration notes / event aliases.
- MCP table: add propose/confirm/mutators; rename list/get status tools.

---

## Implementation order

1. **Rename pass** — DB `slug`, API dual fields, UI labels + stores, MCP aliases. Smoke: existing `langfuse_daily` still lists and runs.
2. **IR + wiring module** — validate edges; unit-free self-check in module docstring/assert demo only if needed (no new test files unless asked).
3. **`propose_workflow` / `confirm_workflow`** — wire through existing `SOURCES` + schedule.
4. **Mutators** — trigger, source, destination, add/remove step + auto-wire.
5. **Workflows page** — list + detail DAG + deep links from MCP `ui_url`.
6. **Docs** — AGENTS.md glossary + MCP table.
7. **Smoke** — NL propose → confirm → appears in UI → add step via MCP → DAG updates → run from Runs.

---

## Done signal

1. No user-facing string says “process” in Control UI (nav, filters, empty states).
2. `propose_workflow` + `confirm_workflow` create a slug’d workflow visible on **Workflows**.
3. `add_workflow_step` / `set_workflow_destination` update IR; graph endpoint reflects new edges without manual edge lists when rules match.
4. `list_workflows` / `get_workflow_status` work; old process tool names still succeed.
5. Event bus: subscribers on `process.*` still receive events; `workflow.*` also published.
6. Runs-first UX from Sprint 8 intact (home = Runs; workflow is filter + definitions page).

---

## Explicit non-goals

- Visual DAG editing / drag connect in React Flow
- Multi-source fan-in authoring beyond what wiring rules support
- Renaming historical event rows in SQLite
- Removing `process_slug` column or `process.*` topics (Sprint 10+ cleanup)

---

## Open questions (resolve before coding if needed)

1. **Slug uniqueness** — global per user? (Recommend: unique per `user_id`.)
2. **Delete semantics** — soft `status=archived` vs hard delete? (Recommend: soft archive.)
3. **Workflows detail chrome** — right panel vs full page? (Recommend: list + right panel.)
