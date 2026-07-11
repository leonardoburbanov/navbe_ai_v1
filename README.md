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
2. Add Navbe to Cursor MCP config (`~/.cursor/mcp.json` on macOS/Linux, `%USERPROFILE%\.cursor\mcp.json` on Windows):

   ```json
   {
     "mcpServers": {
       "navbe": {
         "url": "http://127.0.0.1:7700/mcp/",
         "headers": {}
       }
     }
   }
   ```

   Use **streamable HTTP** (URL), not stdio. Reload MCP / restart the agent so tools appear.

3. In a Cursor chat, confirm the agent can see Navbe tools (e.g. `list_connectors`, `create_langfuse_export_workflow`, `get_process_status`).

Any number of agents can attach to the same daemon. Status is shared — ask from any session how `langfuse_daily` is doing.

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

## Run the MVPs from a Cursor agent

You do **not** need to call tools by hand. Open a Cursor Agent chat with Navbe MCP enabled and speak in natural language. The agent should use Navbe MCP tools under the hood.

### Prerequisites

- Daemon running on `7700`
- Navbe entry in `mcp.json` (above)
- Langfuse host + public/secret keys ready to paste when the agent asks

### MVP A — Monitor Langfuse → local DuckDB

Paste prompts like these (adapt credentials and schedule):

**1. Connect and sync**

> Using Navbe MCP, connect to my Langfuse at `https://<host>` with public key `pk-lf-...` and secret key `sk-lf-...`. Create a DuckDB destination, then schedule a daily incremental export as process `langfuse_daily`. Preview first, then run it for real.

**2. Check progress (any agent / session)**

> How is the Langfuse process going? Subscribe as `cursor` and pull events. Call `get_process_status("langfuse_daily")`.

**3. Analytics**

> Using Navbe, list analysis templates for my DuckDB destination, then query tokens and cost per retailer per day from `mart_retailer_token_cost_daily`.

> How many traces do we have today, per hour?

Example SQL the agent may run via `query_destination` / `query_workflow_destination`:

```sql
SELECT strftime(CAST(timestamp AS TIMESTAMP), '%H') AS hour, count(*) AS traces
FROM traces
WHERE CAST(timestamp AS TIMESTAMP) >= current_date
GROUP BY hour
ORDER BY hour
```

**What the agent should do under the hood**

1. `create_connector` → optional `query_langfuse` sanity check  
2. `create_destination(type="duckdb")`  
3. `create_langfuse_export_workflow` (`process_slug` defaults to `langfuse_daily`)  
4. Optional `preview_workflow`, then `run_workflow`  
5. `subscribe` / `pull_events` / `get_process_status`  
6. `list_analysis_templates` + `query_destination` on the mart  

Watch the same run live in the Control UI (Processes + DAG).

### MVP B — Replay a trace against your API

> Using Navbe MCP, replay Langfuse trace `<trace_id>` from my existing connector against `https://api.example.com/v1/...` with bearer auth. Store results in my DuckDB destination, return the structured diff, and save it as a reusable workflow.

The agent should call `replay_trace_to_api` (with `destination_id` and `save_as_workflow` as needed). Open **Replays** in the Control UI to inspect original output vs API response.

### Multi-agent tip

Start the sync in Cursor, then in Claude or Hermes ask:

> How is `langfuse_daily` doing?

Both read the same hub — same watermark, same events, same process status.

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
