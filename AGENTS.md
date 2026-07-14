# Navbe AI

Workflow automation and orchestration for AI agents.

Navbe turns natural-language intent from external AI agents (Cursor, Claude, Hermes, …) into durable, schedulable, non-linear workflows that move, transform, and analyze data through MCP — starting with Langfuse, designed for many connectors and destinations.

**Jarvis model:** Navbe is a shared local hub. Many workflows can run at once. Many AI agents can author, observe, and subscribe to the same processes. Status is not trapped in one chat session — any subscribed agent can ask *"how is the Langfuse process going?"* and get the same truth.

**Two surfaces, one product:**

| Surface | Role |
| --- | --- |
| **MCP (primary product)** | How AI agents create connections, propose/confirm workflows, schedule, preview, subscribe, and query status. |
| **Desktop / Control UI (human cockpit)** | How humans monitor execution live, inspect a modern DAG, browse connectors/destinations/templates, manage credentials, and intervene (`needs_input`, cancel, preview, switch DB). |

Agents *drive*; the UI *reveals*. Both talk to the same daemon and event bus — never two sources of truth.

This file is the project definition. Agents and humans should treat it as the source of truth for scope, architecture, and conventions.

---

## Problem

AI agents can call tools, but they cannot reliably own recurring data work:

- Credentials, destinations, and schedules need guided elicitation, not one-shot guesses.
- Data movement needs senior-DE behavior: incremental load, dedup, relationships, aggregation, divide-and-conquer under laptop constraints.
- Workflows are not only linear ETL — they branch, loop, compare, and notify.
- Runs must be repeatable without overlapping themselves, and results must surface to *any* interested agent/desktop — not only the session that started the job.
- Several agents may be online at once; they need a shared view of in-flight work (pub/sub), not private side-channels.

**Navbe is the orchestration + event hub** between agents (via MCP) and the data world (connectors → transforms → destinations → templates → notifications).

---

## Product principles

1. **MCP-first product** — The primary *product interface* for automation is MCP. Agents author and control workflows through tools. The desktop does not replace MCP; it observes and assists.
2. **Human cockpit UI** — A desktop (or local web) app is required to monitor runs, visualize the DAG, and explore connectors/destinations — not a nice-to-have afterthought.
3. **Shared hub, many agents** — One Navbe daemon owns processes and state. Cursor, Claude, Hermes, and the Control UI are peers that attach via MCP/HTTP. No agent “owns” a run exclusively.
4. **Pub/sub notifications** — Runs publish events to topics; agents (and UI) subscribe. Status queries read the same store any subscriber would see.
5. **Elicit → confirm → run** — Never silently invent credentials or destinations. Ask, store securely, confirm, then execute.
6. **Data-engineer defaults** — Incremental by watermark, idempotent writes, explicit keys, chunked pulls. Assume 16 GB RAM / local disk.
7. **Graph workflows, not only pipelines** — Triggers, inputs, steps, outputs, branches, joins, retries. Linear is a special case.
8. **Local-first, installable** — Runs on the laptop by default (DuckDB/SQLite). Optional Docker. Desktop app installs the daemon + Control UI (Hermes-style).
9. **Composable integrations** — Langfuse is the first connector, not the product. Same pattern for folders, APIs, warehouses later.
10. **Resilient by evolution** — Schemas, APIs, and workflow IR change. Prefer additive migrate-and-continue over fail-and-stop. Best effort to keep historical data readable.
11. **Destinations are mutable** — Users can switch databases, attach SQL triggers, and preview runs before committing. The hub must support that without rewriting workflows from scratch.
12. **Craft over cleverness** — Modularity, SOLID, KISS, DRY, Clean Code. Smallest clear design that works; refactor when duplication or coupling hurts.
13. **Lazy senior** — Smallest module that works. No Kafka on day one. Local event log + fan-out is enough until it isn’t. YAGNI until a second implementation forces the abstraction.

---

## Three MVP tracks (start here)

### MVP A — Langfuse monitor → local analytics

**User intent (to the agent):**  
*"Monitor my Langfuse every day using Navbe MCP."*

**Guided flow (MCP tools drive this):**

1. **Connect** — Ask for Langfuse host + public/secret keys; validate; store as a named connection.
2. **Destination** — Default DuckDB under the Navbe data dir; offer SQLite. Confirm path.
3. **Workflow** — Create a scheduled graph: trigger (cron) → extract (incremental) → load (deduped) → optional transform → notify.
4. **Templates** — Suggest analysis templates the destination can afford (e.g. tokens/cost by `retailer:[id]` tag).

**Concrete template example:** tokens & cost per `retailer:[retailer_id]`

- Parse tags, extract `retailer_id`.
- Aggregate tokens/cost per retailer per day.
- Store in typed tables (facts + dims), not a dump of raw JSON only.
- Re-run daily with watermark so runs do not re-process the full history.

### MVP B — Trace replay → authenticated API → compare

**User intent:**  
*"Given `langfuse_trace_id`, take input/output, call my API with auth, store results, compare."*

**Guided flow:**

1. Fetch trace I/O from Langfuse connection.
2. Define target API (URL, method, auth scheme: bearer / API key / basic).
3. Map trace input → request body; capture response.
4. Persist request/response + original I/O.
5. Diff/compare (exact, JSON-path, or LLM-assisted later — start with structured diff).
6. Optionally save as a reusable workflow (manual or scheduled batch of trace IDs).

### MVP C — Daily retailer HTML email

**User intent:**  
*"At the end of each day, email me a beautiful HTML report of Langfuse tokens/cost per retailer, comparing days and projecting forward."*

**Guided flow (MCP tools drive this):**

1. **Configure email** — Elicit SMTP host/port/user/password/from; validate; store secrets encrypted (never in workflow IR).
2. **Preview** — Build report from `mart_retailer_token_cost_daily`; write HTML under `~/.navbe/reports/`; confirm layout before sending.
3. **Schedule** — Process `langfuse_daily_report` (default cron `0 23 * * *` UTC) after the daily sync has refreshed the mart.
4. **Send** — HTML email with DoD deltas, 7-day averages, and **7-day run-rate projections** per `retailer_id` (next 7 days + month remainder + MTD). Heuristic only — no ML.

Assumes MVP A mart is populated (`langfuse_daily` with observations). Report workflow does not replace the sync.

All three MVPs share the same orchestration core, connector/destination plugins, scheduler, and notification bus (pub/sub + email channel).

---

## Chosen architecture

### High-level (Jarvis hub)

```text
  Cursor MCP          Claude MCP         Hermes MCP      Control UI / Desktop
       │                   │                  │                 │
       └─────────┬─────────┴────────┬─────────┴────────┬────────┘
                 │   attach as peers (same control plane + bus) │
                 ▼                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│  Navbe daemon (single local hub)                                   │
│  Orchestration │ Scheduler │ Secrets │ Run store │ Registries      │
│  Event bus (pub/sub) — agents + UI subscribe equally               │
└──────────┬─────────────────┬─────────────────┬─────────────────────┘
           ▼                 ▼                 ▼
     Connectors        Transforms        Destinations
     Langfuse          tag / agg         DuckDB / SQLite / email (Resend/SMTP)
                                         (+ notify bus for run events)
     Folder / HTTP     compare / report
```

Many processes run concurrently under the daemon. Agents do not keep private copies of progress — they **subscribe** or **query** the hub. The Control UI is the visual subscriber: live DAG, run timeline, catalog.

### Why LangGraph (and what it is not)

| Choice | Rationale |
| --- | --- |
| **LangGraph** as step runtime | First-class state, branching, cycles, human-in-the-loop interrupts (credential/destination confirm), checkpointing for resume. Fits non-linear agent workflows better than a pure linear DAG runner. |
| **Workflow IR** (JSON) as source of truth | Graphs are serializable, versioned, editable without Python. LangGraph compiles from IR — swap runtime later if needed. |
| **Not** a hosted Temporal/Airflow clone | Overkill for laptop-first MVP. No cluster. One process + SQLite/DuckDB. |
| **Not** "LLM plans every run" | The agent *authors* the workflow once via MCP; the runtime *executes* deterministically on schedule. |

### Overlap-safe scheduling

- One active run per workflow (or per partition key) — lock in the run store.
- Watermark / high-water mark per connector+resource so scheduled runs are incremental.
- Missed ticks: catch-up policy (`skip`, `run_once_catchup`) — default `run_once_catchup` with capped lookback for laptop safety.
- Cron via APScheduler (or equivalent) inside the same process as the MCP server for MVP; extract later if needed.

### Pub/sub notifications (multi-agent)

Navbe is the publisher of truth; AI agents are subscribers. The agent that started a Langfuse sync is not special — Cursor, Claude, and Hermes can all watch the same process.

```text
  Run / scheduler / connector
            │
            ▼ publish(Event)
     ┌──────────────┐
     │  Event store │  append-only (SQLite) — source of truth
     └──────┬───────┘
            │ fan-out
     ┌──────┼──────────────┬─────────────────┐
     ▼      ▼              ▼                 ▼
  Cursor  Claude        Hermes         Control UI
  (poll/  (poll/        (poll/         live DAG +
   SSE)    SSE)          SSE)          tray toasts
```

**Topics (MVP):**

| Topic pattern | Examples |
| --- | --- |
| `run.{run_id}` | step progress, metrics, terminal state |
| `workflow.{slug}` | canonical process-level events (dual-published) |
| `process.{slug}` | alias of `workflow.{slug}` for one sprint |
| `system` | daemon up/down, needs_input globally |

**Event shape (conceptual):** `id`, `ts`, `topic`, `type` (`run.started` / `run.progress` / `run.succeeded` / `run.failed` / `run.needs_input`), `workflow_id`, `run_id`, `slug` (also `process_slug` dual key), `summary`, `metrics?`, `error?`.

**Subscriber model:**

- Each MCP client registers a `subscriber_id` (stable per agent app, e.g. `cursor`, `claude-desktop`, `hermes`, or a UUID per session).
- `subscribe(topics[])` records interest; cursor/offset per subscriber so each agent gets events it has not consumed (independent read positions — classic pub/sub fan-out, not a single shared queue).
- Delivery for MVP: **poll** via MCP (`pull_events`) + optional **SSE** on the HTTP daemon for live clients. No Redis/Kafka — SQLite event log + in-process fan-out. `ponytail: single-node bus → NATS/Redis if multi-machine ever appears`.

**Shared status (not only push):**

- `get_workflow_status(slug | workflow_id)` returns the live picture any agent would see: state, last run, progress %, watermark, recent events.
- Example: user in Hermes asks *"how is the Langfuse process going?"* → same answer as Cursor would get, because both read the hub.

**Also:** desktop OS toasts and the in-app run feed are subscribers of the same bus (not a parallel notification path).

### Control UI / Desktop (human cockpit)

MCP is how agents *act*. The Control UI is how humans *see* and occasionally *steer*.

**Must-have views**

| View | Purpose |
| --- | --- |
| **Live execution** | Workflow/run list, status, step metrics, logs/events, cancel / retry / respond to `needs_input`. |
| **DAG canvas** | Modern visualization of Workflow IR: nodes (connector / transform / destination / control), edges (fan-out, fan-in, conditional), live state coloring per node during a run. Interactive (zoom, focus step, open payload/metrics). |
| **Connectors** | Top-level hub (`?page=connectors`): **Sources** (Langfuse + env credentials) and **Destinations** (DuckDB / SQLite / **email**). Email is a destination type, not a Settings or Email nav category. Settings page is removed; legacy `?page=settings` redirects here. |
| **Reports** | Analysis templates over destinations; email preview/schedule/send live under Connectors → Destinations (email). |
| **Schedules** | Cron, overlap policy, next run, watermark (via Workflows + MCP). |

**DAG design intent**

- Source of truth = Workflow IR from the daemon (read-only canvas in MVP; visual edit can come later).
- Live run overlays node states from the event bus (`pending` / `running` / `succeeded` / `failed` / `skipped`).
- Support non-linear graphs (branches, joins, map/partition) — not only a vertical pipeline.
- Feel contemporary: fluid canvas (e.g. React Flow / XYFlow or equivalent), clear hierarchy, motion used for state changes — not a legacy Airflow grid clone.

**Architecture of the UI**

- Same monorepo: `apps/desktop` hosts the shell; UI talks to the local daemon over HTTP/SSE (and may call the same APIs MCP uses under the hood).
- **No second backend** — Control UI is a client of the hub, like any agent.
- Installer starts/stops the daemon; tray shows in-flight process count and last failures.
- Optional: open the same UI in a browser against localhost for flexibility; desktop wrapper is the default distribution.

### Local folders as input

- First-class connector: watch or batch-read a directory (glob, optional file stability delay).
- Same incremental contract as Langfuse (cursor = mtime/inode or content hash).
- Useful for dropping exports, fixtures, or API response dumps into a workflow.

### Deployment model (Hermes-like)

| Mode | Use |
| --- | --- |
| **Local daemon** (HTTP MCP + SSE + UI API) | **Default hub** — owns schedules, concurrent runs, event bus, registries. Agents + Control UI attach here. |
| **CLI + MCP stdio** | Thin client that talks to the daemon (or embeds for single-agent dev). Prefer daemon so peers share state. |
| **Desktop + Control UI** | Installer, tray, **live monitor**, **DAG canvas**, catalog, credentials — first-class human surface on the same bus |
| **Docker** | Optional headless / CI; mount data volume; UI optional via published port |

**Concurrency:** many workflows/runs in parallel under one daemon; per-workflow overlap locks still apply. Agents never spawn isolated private runtimes for the same profile.

Data and config live under a profile home, e.g. `~/.navbe/` (or `%USERPROFILE%\.navbe\` on Windows): connections, secrets, DuckDB files, workflow IR, run history, **event log**, subscriber offsets.

---

## Monorepo layout

Hermes-inspired: one repo, clear packages, thin apps. Python with `uv` workspaces; desktop later with Tauri or Electron calling the same CLI/daemon.

```text
navbe_ai_v1/
├── AGENTS.md                 # this file
├── pyproject.toml            # uv workspace root
├── packages/
│   ├── navbe_core/           # Workflow IR, LangGraph compile, run store, secrets
│   ├── navbe_mcp/            # FastMCP tools + elicitation flows
│   ├── navbe_scheduler/      # Cron, locks, watermarks
│   ├── navbe_notify/         # Pub/sub event bus, subscribers, SSE, desktop bridge
│   ├── navbe_connectors/     # Plugin package: langfuse, folder, http
│   ├── navbe_destinations/   # Plugin package: duckdb, sqlite
│   ├── navbe_transforms/     # Reusable steps: tag parse, aggregate, compare
│   └── navbe_api/            # Optional thin HTTP API for Control UI (same hub ops as MCP)
├── apps/
│   ├── cli/                  # `navbe` entrypoint (mcp, run, status, daemon)
│   ├── web/                  # Control UI (DAG, monitor, catalog) — Next.js or Vite+React
│   └── desktop/              # Native shell (Tauri/Electron) wrapping apps/web + daemon lifecycle
├── docker/                   # optional Dockerfile + compose
└── examples/                 # only when explicitly requested
```

**Import rule:** apps → packages; connectors/destinations/transforms depend on `navbe_core` only; MCP/API depend on core + plugins via registry. Control UI never embeds business logic that bypasses the daemon. No circular imports.

---

## Core domain model

### Workflow IR (conceptual)

```text
Workflow
  id, name, version
  trigger: manual | cron | mcp_tool | folder_event
  nodes: [ Node ]
  edges: [ Edge ]          # supports fan-out / fan-in / conditional
  params: schema           # elicited inputs (connection_id, destination_id, …)
  schedule?: cron + tz + overlap_policy
  notify?: channels[]

Node
  id, type: connector | transform | destination | control | notify
  config: {...}
  # control = branch | join | human_confirm | map (divide-and-conquer)
```

### Run model

- `Run`: workflow_id, status, started_at, finished_at, trigger, watermark_in/out, error, `slug?`
- `RunStep`: node_id, status, attempt, metrics (rows_in/out, bytes), artifact refs
- Checkpoint: LangGraph thread_id ↔ run_id for resume after `needs_input` or crash
- `slug`: friendly handle on the workflow (`langfuse_daily`) — what humans/agents name in chat (legacy column `process_slug` still dual-written)

### Event & subscriber model

- `Event`: append-only bus row (topic, type, payload, ts)
- `Subscriber`: `subscriber_id`, label (`cursor` / `claude` / `hermes` / `desktop`), last_seen
- `Subscription`: subscriber_id + topic pattern
- `SubscriberCursor`: last event_id consumed per subscriber (independent offsets)

### Connection & destination

- `Connection`: type (`langfuse`, `http`, `folder`, …), encrypted secrets, probe/validate
- `Destination`: type (`duckdb`, `sqlite`, …), path/DSN, schema version, optional engine-specific options
- Destinations are **swappable**: a workflow references `destination_id` (or a logical name), not a hard-coded file path in every node
- `DestinationTrigger`: user- or template-defined SQL trigger (or engine equivalent) bound to a destination table/event; versioned with the schema
- Analysis templates bound to destination capabilities (SQL files or parameterized queries)
- **Preview run**: execute a workflow (or step subset) against a scratch schema / temp DB / `LIMIT`ed extract — no watermark advance, no subscriber “success” for the production process unless explicitly promoted

### Destination operations (change anytime)

Users and agents must be able to reshape the data plane without discarding the orchestration:

| Operation | Behavior |
| --- | --- |
| **Change database** | Point a workflow or profile at a new destination (new DuckDB file, SQLite file, or later another engine). Offer migrate/copy curated marts when possible; confirm before destructive switch. |
| **Retarget mid-life** | `destination_id` on the workflow updates; next run uses the new target. Old DB left intact unless user asks to delete. |
| **Add / update / drop triggers** | Register SQL triggers (or DuckDB equivalents) via MCP; stored in control plane + applied on destination open. Evolve with schema migrations. |
| **Preview** | `preview_workflow` runs dry: sample rows, explain plan / row counts, write only to preview sandbox. Production watermarks and locks unchanged. |
| **Promote preview** | Optional explicit step to apply preview DDL/trigger diffs to production after user confirm. |

Engine differences are behind the destination plugin interface — workflows stay engine-agnostic; triggers that are engine-specific are validated by the active plugin and rejected clearly if unsupported.

### Data-engineering contracts (every connector)

1. **Extract** in pages/chunks (never full dump into RAM).
2. **Watermark** field documented (e.g. Langfuse `fromTimestamp`).
3. **Natural key** for dedup (e.g. `trace_id`, `observation_id`).
4. **Load** upsert/insert-only-if-new into destination.
5. **Relationships** declared (trace → observations → scores) so transforms join correctly.
6. **Divide-and-conquer**: `map` node over partitions (day, tag prefix, file batch) with bounded concurrency (default 1–2 on 16 GB machines).

### Schema evolution & resilient workflows

Workflows must survive connector API drift, new/removed fields, destination upgrades, and Navbe version bumps. Default posture: **best-effort evolve and continue**, not brittle fail-on-mismatch.

**Destination / analytics schema**

1. **Versioned DDL** — every destination schema has a monotonic `schema_version`; migrations are ordered, idempotent scripts (or declarative apply) stored in-repo.
2. **Additive first** — prefer `ADD COLUMN` / new tables / new marts. Avoid renames and type narrowing in place.
3. **Expand → backfill → contract** — if a breaking change is unavoidable: add the new shape, dual-write or backfill, switch readers (templates), only then drop old columns in a later version.
4. **Raw + curated** — land flexible raw/JSON (or wide “as received”) tables; curated marts are strict. Raw absorbs upstream surprise; marts evolve via migrations.
5. **Unknown fields** — extra keys from Langfuse (or any connector) go into a `payload` / `extras` JSON column; never drop the row because of an unexpected field.
6. **Missing fields** — nullable columns + defaults; transforms skip or null-fill rather than aborting the whole run when a non-key field disappears.
7. **Type coercion** — best-effort cast (string timestamps, numeric strings); on failure keep raw value in extras and emit a `schema.warning` event — do not fail the run unless a **natural key** or required watermark field is broken.
8. **Template compatibility** — analysis templates declare `min_schema_version`; if the destination is behind, auto-migrate before query when safe, else return `needs_migration` with the exact step.

**Workflow IR & control plane**

- IR is forward-compatible: unknown node config keys are ignored with a warning; known required keys still elicit/`needs_input`.
- Control-plane SQLite migrations run automatically on daemon start (best effort, transactional).
- Checkpoints: if a mid-run schema/IR upgrade makes a checkpoint unreadable, mark run `needs_input` / `failed_recoverable` and allow resume from last good watermark — never corrupt the destination to “force” progress.

**Connector contract drift**

- Probe responses; if the upstream shape changes, prefer mapping adapters versioned per connector (`langfuse@v1` → `v2`) over rewriting historical tables.
- Publish `schema.changed` / `schema.warning` on the event bus so any subscribed agent can see drift without the run dying silently.

**What “best effort” does *not* mean**

- Silent data loss, destructive migrations without a backup/notice, or inventing key values.
- Continuing when natural keys or watermarks cannot be established — that *does* fail the run loudly.

---

## MCP tool surface (MVP)

Tools should feel like *workflows*, not raw SDK wrappers. Prefer fewer, higher-level tools with clear next-step hints in responses.

| Tool | Purpose |
| --- | --- |
| `list_connectors` / `create_connector` / `get_connector` / `update_connector` / `delete_connector` | Source connector CRUD |
| `upsert_connector_env` / `delete_connector_env` / `test_connector` | Per-env credentials + probe |
| `list_destinations` / `create_destination` | Destinations including `duckdb`, `sqlite`, `email` |
| `update_destination` / `switch_destination` | Change DB path/engine anytime; optional data migrate; confirm |
| `list_destination_triggers` / `upsert_destination_trigger` / `delete_destination_trigger` | Manage SQL/engine triggers on the data plane |
| `propose_workflow` | NL intent → draft IR (not running yet); returns draft + needs_input |
| `confirm_workflow` | Persist draft IR + slug + optional schedule |
| `list_workflows` | All workflows: slug, schedule, nodes, last run |
| `get_workflow_status` | Shared live status by `slug` or `workflow_id` (any agent) |
| `update_workflow` / `delete_workflow` | Patch metadata / soft-archive |
| `set_workflow_trigger` / `set_workflow_source` / `set_workflow_destination` | Bind trigger + connector (+ optional `connector_env`) + destination |
| `set_workflow_step_connector` | Per-step `graph.node_config` override (connector/env/config) |
| `add_workflow_step` / `remove_workflow_step` / `connect_workflow_steps` | Mutate graph; auto-wire edges when unambiguous |
| `list_analysis_templates` | Templates affordable for current destination |
| `preview_workflow` | Dry/sandbox run: sample, validate schema/triggers, no prod watermark advance |
| `run_workflow` | Manual run now (production) |
| `schedule_workflow` | Attach cron + overlap policy |
| `get_run` / `list_runs` | Status and metrics |
| `get_process_status` / `list_processes` | Deprecated aliases for get_workflow_status / list_workflows |
| `suggest_workflow` | Deprecated alias for propose_workflow |
| `subscribe` / `unsubscribe` | Register interest in topics (`workflow.langfuse_daily`, `process.*`, `run.*`, …) |
| `pull_events` | Poll bus since subscriber cursor (multi-agent fan-out) |
| `replay_trace_to_api` | MVP B one-shot or save-as-workflow |
| `configure_resend` | Store Resend API key; upsert destination `type=email`; `ui_url` → Connectors Destinations |
| `configure_email` | SMTP fallback; same email destination upsert |
| `preview_daily_report` | Build HTML retailer report to `~/.navbe/reports/` (no send) |
| `schedule_daily_report` | Schedule `langfuse_daily_report` end-of-day email (default `0 23 * * *`) |
| `send_daily_report` | Run report workflow now and send HTML email |

**Elicitation pattern:** if required config is missing, return a structured `needs_input` payload (fields, secrets, defaults) instead of failing opaquely. Desktop/CLI/agent then supply values via follow-up tool call.

---

## Laptop constraints (non-negotiable for defaults)

- Target: **16 GB RAM**, large local disk.
- DuckDB file size can grow — prefer partitioned tables / date keys; document vacuum/retention later.
- Default page size for Langfuse pulls: conservative (e.g. 50–100); configurable.
- Default map concurrency: **1** (safe); max 2–4 only when user opts in.
- No Spark, no Kubernetes, no remote warehouse required for MVP.

---

## Tech stack (decisions)

| Layer | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.12+ | Match existing Navbe services |
| Packaging | `uv` workspaces | Mandatory for Python deps |
| MCP | FastMCP | Align with `navbe_ai_orchestrator_backend` |
| Runtime | LangGraph + checkpointer | SQLite checkpointer for local |
| OLAP store | DuckDB | Default destination |
| OLTP / control plane | SQLite | Workflows, runs, secrets metadata |
| Scheduler | APScheduler AsyncIO | Same process as daemon for MVP |
| Event bus | SQLite append-only + in-process pub/sub | Poll MCP + optional SSE; not Kafka |
| Email notify | Resend API (primary) or SMTP | HTML reports; secrets Fernet-encrypted in `~/.navbe` |
| Secrets | OS keyring or Fernet at rest in `~/.navbe` | Never in workflow IR plaintext |
| Control UI | Vite+React + DAG canvas | Runs, Workflows, Reports, **Connectors** (sources / destinations); `pnpm` |
| Desktop shell | Tauri (preferred) or Electron | Installer + tray; loads Control UI; manages daemon |
| Containers | Docker optional | Daemon + volume for `~/.navbe`; UI optional |

MCP remains the agent product. Control UI + desktop are the human product surface — both ship in the monorepo and share the daemon.

---

## Phased delivery

### Phase 0 — Skeleton

- Monorepo + `uv` workspace + `navbe` CLI (`mcp`, `version`).
- Empty registries for connectors/destinations.
- SQLite control plane schema (connections, destinations, workflows, runs, events, subscribers).
- Daemon-first entry so multiple MCP clients can attach to one hub.

### Phase 1 — MVP A vertical slice

- Langfuse connector (incremental traces/observations).
- DuckDB destination + schema for traces/observations + retailer tag aggregates.
- One cron workflow + overlap lock + watermark + `process_slug`.
- MCP tools for connect → destination → confirm → schedule → list templates.
- Pub/sub: publish run events; `subscribe` + `pull_events` + `get_process_status` (verify from two different agent clients).
- `preview_workflow` sandbox path (no watermark advance).
- **Control UI v0:** process/run monitor + connector/destination catalog (read-only), fed by daemon SSE/API.

### Phase 2 — MVP B + visual DAG

- `replay_trace_to_api` + auth config + result store + structured compare.
- Save replay as reusable workflow IR.
- `switch_destination` + destination triggers (create/list/delete) with confirm.
- **DAG canvas:** render Workflow IR, live node states during runs, non-linear edges.
- Desktop shell (tray + daemon lifecycle) packaging the Control UI.

### Phase 3 — MVP C daily email report (Sprint 5)

- SMTP configure + encrypted secrets; HTML retailer report (DoD, 7d, run-rate projections).
- Process `langfuse_daily_report` (end-of-day cron); `preview_daily_report` / `send_daily_report`.
- Bus events `report.previewed` / `report.sent` / `report.failed`.

### Phase 4 — Hardening

- Local folder connector.
- Richer UI: credentials editors, trigger management, preview promote, schedule editor, email settings.
- Docker compose for headless.
- Second connector only when a real user asks — prove the plugin API.

---

## Best practices

### Software craft (mandatory)

Apply these on every change. If a design violates them, simplify before merging complexity.

| Principle | In Navbe practice |
| --- | --- |
| **Modularity** | Packages and plugins with clear boundaries (`connectors` / `destinations` / `transforms` / `notify`). Apps stay thin. A feature that needs three packages to “know” each other’s internals is wrong — use registries and IR. |
| **S — Single responsibility** | One module/class/function does one job. `repository` ≠ orchestration ≠ MCP shaping. Destination plugin applies DDL; it does not schedule cron. |
| **O — Open/closed** | Add a connector/destination/node by registering a plugin, not by editing a central `if/elif` god-switch (beyond a single import side-effect). |
| **L — Liskov** | Every destination plugin honors the same contract (open, migrate, load, preview, apply_triggers). No “DuckDB-only” surprise methods required by core. |
| **I — Interface segregation** | Small protocols: `Extractor`, `Loader`, `Previewable`, `TriggerSupport`. Do not force folder connectors to implement Langfuse APIs. |
| **D — Dependency inversion** | Core depends on abstractions (IR + registries), not on Langfuse SDKs. Concrete plugins depend inward on `navbe_core`. |
| **KISS** | Linear code over frameworks. No microservices inside the laptop hub. Prefer a function over a strategy hierarchy until a second implementation exists. |
| **DRY** | Shared watermark/dedup/load helpers live once in core or transforms. Do not copy SQL migrations per template — version them centrally. |
| **Clean Code** | Intention-revealing names; small functions; early returns; no commented-out corpses; errors with context; public APIs typed + docstringed. Boy-scout: leave the module clearer than you found it. |

**Conflict resolution:** KISS wins over speculative SOLID abstractions. DRY wins over copy-paste. Readability wins over clever one-liners. When unsure, delete.

### Architecture

- **Workflow IR is the contract**; Python nodes implement typed handlers registered by name.
- **Plugins self-register** at import (Hermes-style registry). Adding Langfuse does not edit a central switch-case beyond an import side-effect.
- **Control plane (SQLite) ≠ data plane (DuckDB).** Never mix run metadata into analytics tables.
- **Destination behind an interface** — switching DB or engine must not rewrite workflow graphs; only `destination_id` / plugin config changes.
- **Preview ≠ production** — previews never advance watermarks or clear overlap locks; publish `run.preview.*` events, not success on `process.{slug}` unless promoted.
- **Idempotent steps:** re-running a successful extract+load with the same watermark must not duplicate facts.
- **Evolve schemas, don’t shatter runs:** additive migrations, raw+mart split, extras for unknown fields; fail only on key/watermark breakage.
- **Human-in-the-loop nodes** for credentials and destination confirmation; do not bypass in “agent autofill” without an explicit flag.
- **One hub per profile** — agents are clients; they must not each start a conflicting scheduler on the same `~/.navbe`.
- **Control UI is a peer client** — no private database; everything via daemon API/SSE/bus. DAG reads IR + run events only.
- **MCP and UI expose the same capabilities** over time; UI may lag MCP for authoring, but never invents shadow state.

### Code

- Type hints and docstrings on all public functions.
- One responsibility per module; prefer deleting code over adding layers.
- Mark intentional shortcuts with `ponytail: <ceiling> → <upgrade>`.
- No new dependencies if stdlib / existing stack covers it.
- No tests, examples, or extra markdown unless explicitly requested.
- No god-files: if a module mixes MCP I/O, SQL, and business rules, split it.

### Security

- Secrets only in secret store; tools return redacted connection views.
- MCP over stdio locally by default; HTTP daemon binds localhost unless configured.
- Validate SSL and URLs for Langfuse/API connectors.
- User-supplied trigger SQL is a trust-boundary: run only against the chosen destination, never against the control plane; validate/parse before apply.

### Agent UX

- Tool responses include **next_step** hints (`create_destination`, `confirm_workflow`, `preview_workflow`, …).
- Prefer one conversational path that chains tools over exposing 50 low-level RPCs.
- Offer **preview before schedule** when creating or changing destinations, triggers, or transforms.
- Scheduled workflows run without the chat session; any agent recovers state via `get_workflow_status` / `pull_events`.
- On attach, agents should `subscribe` to relevant `workflow.*` topics (or `workflow.*` / `process.*` wildcard) so they stay aligned with peers.

### Data

- Define schemas before first load (DuckDB DDL versioned in-repo); apply migrations on destination open / daemon start.
- Raw landing tables + curated marts (e.g. `mart_retailer_token_cost_daily`); templates query marts.
- Treat upstream schema change as a normal event: adapt, warn on the bus, keep history queryable.
- Changing the database is a first-class operation: confirm, optionally migrate, keep the old file until the user deletes it.
- Triggers are schema-versioned artifacts; dropping a table must consider dependent triggers.

---

## Non-goals (for now)

- Multi-tenant SaaS control plane.
- Replacing Langfuse UI.
- Training / fine-tuning pipelines.
- Arbitrary user-supplied Python as workflow steps (security); stick to registered node types.
- Real-time streaming (batch + frequent cron is enough).

---

## Success criteria for MVP

1. From Cursor: agent connects Langfuse via Navbe MCP, confirms DuckDB, schedules daily incremental sync, and can query/report tokens & cost by `retailer_id` tag.
2. From Cursor: agent replays a `langfuse_trace_id` against an authenticated API, stores results, and returns a comparison.
3. Second scheduled run does not duplicate rows and does not overlap an in-flight run.
4. While a Langfuse workflow runs, **Hermes and Claude** (separate MCP clients) can both call `get_workflow_status("langfuse_daily")` / `pull_events` and see the same progress; completion fans out to all subscribers.
5. After a non-breaking destination/connector schema change, the next scheduled run migrates (if needed) and completes without manual rebuild; agents see `schema.warning` / `schema.changed` events when drift was absorbed.
6. User can preview a workflow, switch the destination database, and add a destination trigger via MCP without rewriting the workflow IR from scratch.
7. Control UI shows live execution and a modern DAG for the Langfuse workflow; catalog lists available connectors/destinations; UI and MCP agree on process status.
8. End-of-day: agent configures SMTP, previews HTML retailer report, schedules `langfuse_daily_report`; email arrives with DoD comparisons and 7-day run-rate projections per `retailer_id` matching the mart.

---

## Glossary

| Term | Meaning |
| --- | --- |
| Connector | Source that pulls or receives data (Langfuse, folder, HTTP); credentials live in **environments** (`staging` / `testing` / `prod` / custom) |
| Connector environment | Named credential pack on a connector; Fernet-encrypted secrets; workflow binds `connector_env` (default) or per-step override |
| Destination | Where results land or are delivered: DuckDB, SQLite, or **email** (Resend/SMTP notify destination) |
| Connectors hub | Control UI page (`?page=connectors&tab=sources\|destinations`) — human credential surface for sources and destinations |
| Workflow | Durable IR + schedule + slug; what agents and the Control UI name |
| Workflow IR | Serializable graph definition |
| Template | Packaged analysis or workflow recipe |
| Watermark | Incremental cursor for extract |
| Run | One execution instance of a workflow; stores `duration_ms` wall-clock total |
| Run step | One LangGraph node within a run (`workflow_run_steps`); stores per-step `duration_ms` |
| Slug | Friendly handle on a workflow (`langfuse_daily`); legacy alias: process_slug / “process” |
| Process | Deprecated synonym of workflow slug — keep only in event/API aliases |
| Event bus | Append-only pub/sub log shared by all agents |
| Subscriber | An AI agent or UI client with its own event cursor |
| Schema version | Monotonic destination/control-plane DDL generation; migrations are additive-first |
| Extras / payload | JSON column that absorbs unknown upstream fields without failing the load |
| Preview | Sandbox/dry run that does not advance production watermarks |
| Destination trigger | Engine SQL trigger (or equivalent) managed via Navbe and applied to the data plane |
| Control UI | Human cockpit: monitor, DAG, Workflows, Reports, **Connectors** (sources / destinations including email) |
| DAG canvas | Interactive visualization of Workflow IR with live run state |
| Elicitation | Structured ask for missing config/secrets |
| Daily email report | HTML email from retailer mart (DoD + 7d run-rate projections) via Resend/SMTP email destination |

---

## Working agreement for coding agents

1. Read this file before adding packages or changing architecture.
2. Prefer extending registries over inventing parallel systems.
3. Implement MVP A before generalizing plugin frameworks beyond what A needs — but keep folder shapes ready for B.
4. Use `uv` for Python; keep the monorepo installable with one `uv sync` at root.
5. When unsure, choose the laptop-safe, incremental, idempotent option.
6. When schemas drift, choose evolve-and-continue (additive + extras + warn) over drop-and-recreate, unless the user explicitly asks for a rebuild.
7. Obey modularity, SOLID, KISS, DRY, and Clean Code; if principles conflict, KISS + readability win over speculative abstraction.
8. Never hard-code a single database file into workflow logic — destinations are swappable; prefer preview before destructive production runs.
9. Keep MCP the agent product and Control UI the human cockpit; both share one daemon — do not build a second orchestration path inside the frontend.
10. Human credential and destination surface is the **Connectors** page (Sources | Destinations); do not reintroduce a Settings page or a top-level Email category — email is destination `type=email`.
