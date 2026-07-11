# Navbe

**Local workflow hub for AI agents.**

Navbe turns agent intent into durable, schedulable data workflows. Agents connect through MCP; humans monitor through a Control UI. One daemon owns state, schedules, and the event bus — so Cursor, Claude, Hermes, and the cockpit all see the same truth.

| Surface | Role |
| --- | --- |
| **MCP** | Primary product interface — connect, schedule, preview, subscribe, query status |
| **Control UI** | Human cockpit — live processes, runs, catalog, DAG canvas, replays |

---

## Requirements

| Tool | Version |
| --- | --- |
| Python | 3.12+ |
| [uv](https://docs.astral.sh/uv/) | latest |
| Node.js | 20+ |
| [pnpm](https://pnpm.io/) | 9+ |

---

## Install

```bash
git clone <repo-url> navbe_ai_v1
cd navbe_ai_v1

# Python workspace
uv sync

# Control UI
cd apps/web && pnpm install && cd ../..
```

Verify the CLI:

```bash
uv run navbe version
# → navbe 0.1.0
```

---

## Start the daemon

```bash
uv run navbe daemon
```

Defaults: `http://127.0.0.1:7700`

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `/mcp` | MCP (streamable HTTP) — connect your agent here |
| `/events/sse` | Live event stream for the Control UI |
| `/api/*` | REST for the Control UI |

Optional flags:

```bash
uv run navbe daemon --host 127.0.0.1 --port 7700
```

Profile data lives under `~/.navbe` (or `%USERPROFILE%\.navbe` on Windows). Override with `NAVBE_HOME`.

---

## Connect Cursor (MCP)

1. Start the daemon (`uv run navbe daemon`).
2. In Cursor MCP settings, add a server pointing at:

   ```text
   http://127.0.0.1:7700/mcp
   ```

   Use **streamable HTTP** transport (not stdio).

3. Confirm tools appear (e.g. `list_connectors`, `create_langfuse_export_workflow`, `get_process_status`).

Any number of agents can attach to the same daemon. Subscribe with a stable `subscriber_id` (`cursor`, `claude`, …) and poll with `pull_events`, or ask `get_process_status("langfuse_daily")`.

---

## Control UI

With the daemon running:

```bash
cd apps/web
pnpm dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` and `/events` to port `7700`.

| Page | What you see |
| --- | --- |
| **Processes** | Named processes (`langfuse_daily`, …) and live status |
| **Runs** | Run history for a selected workflow |
| **Catalog** | Connectors, destinations, analysis templates |
| **DAG** | Workflow graph with live step coloring via SSE |
| **Replays** | Trace replay results and diffs |

---

## First workflow (Langfuse → DuckDB)

From an MCP-connected agent (or by calling the same tools yourself):

1. **`create_connector`** — Langfuse host + public/secret keys  
2. **`create_destination`** — `type: "duckdb"` (path defaults under the profile data dir)  
3. **`create_langfuse_export_workflow`** — wires connector → destination; default `process_slug` is `langfuse_daily`  
4. **`preview_workflow`** (optional) — sample run; does not advance watermarks  
5. **`run_workflow`** — production incremental sync + retailer mart refresh  
6. **`list_analysis_templates`** / **`query_destination`** — e.g. tokens & cost per `retailer:[id]` tag  

Check shared status from any agent:

```text
get_process_status("langfuse_daily")
subscribe(subscriber_id="cursor") → pull_events(...)
```

### Trace replay (MVP B)

```text
replay_trace_to_api(
  trace_id=...,
  connection_id=...,
  api_url=...,
  auth={ "type": "bearer", "token": "..." },
  destination_id=...,      # optional: persist to replay_results
  save_as_workflow=true    # optional: reusable process replay_<id>
)
```

Results appear on the **Replays** page and via `GET /api/replays`.

---

## Quality checks

```bash
# Python: lint, types, tests (includes mocked MVP cycle e2e)
make check

# Control UI
cd apps/web && pnpm check && pnpm test
```

E2E only:

```bash
uv run pytest packages/navbe_core/tests/test_mvp_cycle_e2e.py -q
```

---

## Repository layout

```text
navbe_ai_v1/
├── AGENTS.md                 # Product & architecture source of truth
├── packages/
│   ├── navbe_core/           # Workflow IR, LangGraph, runs, secrets
│   ├── navbe_mcp/            # MCP tool registry
│   ├── navbe_api/            # FastAPI: MCP mount, REST, SSE
│   ├── navbe_notify/         # Durable event bus
│   ├── navbe_scheduler/      # Cron / overlap-safe scheduling
│   ├── navbe_connectors/     # Langfuse (and later folder/HTTP)
│   ├── navbe_destinations/   # DuckDB / CSV
│   └── navbe_transforms/     # Tag parse, retailer mart SQL
├── apps/
│   ├── cli/                  # `navbe` entrypoint
│   └── web/                  # Control UI (Vite + React)
└── Makefile
```

For architecture, principles, and the full MCP tool surface, see [AGENTS.md](AGENTS.md).

---

## Troubleshooting

| Symptom | Check |
| --- | --- |
| MCP tools missing | Daemon running? URL ends with `/mcp`? Streamable HTTP selected? |
| Control UI empty / network errors | Daemon on `7700`? `pnpm dev` proxy to `127.0.0.1:7700`? |
| Wrong profile / stale DB | Inspect `NAVBE_HOME` (default `~/.navbe`) |
| Port in use | `uv run navbe daemon --port 7701` and update MCP + UI proxy |

---

## License

Proprietary — Navbe AI. All rights reserved unless otherwise noted.
