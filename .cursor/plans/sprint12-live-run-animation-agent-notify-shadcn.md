# Sprint 12 — Live run animation, agent result notify, shadcn UI

When a workflow is triggered, the Control UI should **auto-open that run** and show an **animated live DAG**. When the run finishes, the **Cursor (MCP) agent** gets a clear result message. Upgrade the Control UI to the **shadcn + Base UI** design system so the cockpit feels coherent and modern.

**User pain:** *“I start a run and want to watch it animate in the UI; when it’s done, tell my Cursor agent what happened — and make the UI look like a real product, not raw HTML.”*

---

## Defaults (locked)

| Knob | Choice | Why |
| --- | --- | --- |
| Auto-open surface | **Runs page** + **left run sheet** (`?page=runs&workflow=…&run=…`) | Matches Sprint 8; DAG lives in the sheet |
| Auto-open trigger | SSE `run.started` **and** deep-link `run=` on load | MCP already returns `live_url`; UI must react without refresh |
| Animation | Node pulse + edge flow while `running`; settle color on terminal | XYFlow already colors status — add motion, don’t rebuild canvas |
| Agent notify path | **Event bus** → subscriber `cursor` via `pull_events` (+ optional MCP `notifications/message` if FastMCP supports it) | Jarvis model: agents are subscribers; Cursor has no public “inject chat” API |
| Result payload | Structured `agent_message` + existing metrics / `duration_ms` / error | Agents get one readable summary without scraping run dump |
| Design system | **shadcn/ui + Base UI + Tailwind** in `apps/web` | User ask; Base UI is current shadcn default (not Radix-only) |
| Scope of redesign | Shell, Runs, run sheet, Connectors, Workflows, Reports — shared primitives first | Migrate pages onto shared Button/Badge/Sheet/Table; no greenfield rewrite |

**Out of scope:** OS tray toasts; Cursor IDE marketplace extension; inventing a ChatGPT-style push into the chat thread; full visual IR editor; replacing XYFlow; dark-mode-only theme; portfolio of unused shadcn components.

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| Run starts; UI may stay on another page / closed sheet | Sprint 7/8 deep links exist, but auto-navigation on live SSE `run.started` is incomplete / inconsistent |
| DAG status changes feel static | Status colors only — no pulse, edge animation, or step-sequence motion |
| Agent learns result only if it polls / re-asks | Terminal events publish, but no Cursor-facing **result message** contract or auto-surface hint |
| UI is bespoke CSS / ad-hoc markup | `apps/web` has React + XYFlow + Zustand; **no** Tailwind / shadcn / Base UI |

---

## Goal

With `navbe daemon` + `pnpm dev` in Control UI + Cursor MCP attached:

1. Trigger a workflow (MCP `run_workflow`, schedule, or UI) → Control UI **navigates to that run** and opens the run sheet with a **live animated DAG** (nodes/edges reflect step progress).
2. On `run.succeeded` / `run.failed` / `run.cancelled` → Cursor subscriber receives a crisp **result message** (status, slug, duration, key metrics, error if any, `live_url` for the finished run).
3. Control UI uses **shadcn Base UI** primitives (layout shell, buttons, badges, sheet, table, tabs) — pages look consistent; motion for live runs still works on top.

---

## Architecture

```text
 run_now / schedule / UI trigger
        │
        ▼ publish(run.started)
 ┌──────────────────┐
 │ Event bus        │──► SSE ──► Control UI
 └────────┬─────────┘              ├─ navigate ?page=runs&workflow&run
          │                        ├─ open RunDetailSheet
          │                        └─ animate DAG (pulse / edges)
          │
          ▼ publish(run.succeeded | failed | cancelled)
               payload.agent_message = "…"
          │
          ├─► pull_events(subscriber_id=cursor)  → agent sees result
          └─► (optional) FastMCP notification     → client surfaces sooner
```

**ponytail:** reuse Sprint 7 SSE + Sprint 8 sheet; do not add WebSocket. Agent notify = richer bus event + pull path; optional MCP notification only if one call-site stays small.

**ponytail:** shadcn install once (Tailwind v4 + `components.json` + Base UI); wrap existing pages — delete ad-hoc button/badge classes as you touch them, don’t dual-system forever.

---

## 1. Auto-open live animated run

### Behavior

- On SSE `run.started` (and on load when URL has `run=`): set page to `runs`, select workflow filter if present, **open left sheet** for that `run_id`.
- If the sheet is already open on another run, switch to the new in-flight run (most recent trigger wins; don’t spawn N sheets).
- While steps run: DAG nodes use `running` pulse / glow; edges show subtle animated dash or progress toward the next node; completed nodes settle to succeeded/failed colors (Sprint 3 color map stays source of truth).
- Prefer existing `dagStore` + `run.step.started` / `run.step` events; ensure mid-run animation uses the same store (no second status pipeline).

### Files (indicative)

- [`apps/web/src/App.tsx`](apps/web/src/App.tsx) / routing query sync
- [`apps/web/src/api/sse.ts`](apps/web/src/api/sse.ts)
- [`apps/web/src/pages/RunsPage.tsx`](apps/web/src/pages/RunsPage.tsx)
- [`apps/web/src/components/RunDetailSheet.tsx`](apps/web/src/components/RunDetailSheet.tsx)
- DAG node components under `apps/web/src/components/` (or `dag/`)
- `live_url` helpers already return Runs deep links — keep MCP `live_url` aligned

### Done slice

Manual or scheduled run → UI focuses the run sheet without clicking the row; nodes visibly animate through the graph.

---

## 2. Notify Cursor agent with run result

### Behavior

On terminal run events (`succeeded` / `failed` / `cancelled`), publish bus payload that includes:

```json
{
  "type": "run.succeeded",
  "run_id": "…",
  "workflow_id": "…",
  "slug": "langfuse_daily",
  "duration_ms": 12345,
  "metrics": { "…": "…" },
  "agent_message": "Workflow langfuse_daily succeeded in 12.3s — 1,204 traces loaded. Open: http://127.0.0.1:5173/?page=runs&run=…"
}
```

- Subscriber model unchanged: Cursor MCP client should `subscribe` to `workflow.*` / `run.*` (document in tool `next_step` after `run_workflow`).
- `pull_events` returns events that include `agent_message` so any agent turn that polls gets the result text verbatim.
- Optional stretch: if FastMCP supports server→client notifications, emit one on terminal events for `subscriber_id=cursor` — only if it stays a thin adapter over the same payload.

**Not doing:** guessing Cursor internal chat APIs; emailing the human; blocking the run until an agent ACKs.

### Files (indicative)

- [`packages/navbe_core/navbe_core/agent.py`](packages/navbe_core/navbe_core/agent.py) — build `agent_message` at complete/fail/cancel
- [`packages/navbe_notify/`](packages/navbe_notify/) / publish call sites
- MCP: [`subscribe`](packages/navbe_mcp/) / [`pull_events`](packages/navbe_mcp/) response shape (pass through `agent_message`)
- Brief glossary note in [`AGENTS.md`](AGENTS.md) if the contract is new

---

## 3. shadcn Base UI design system

### Defaults

| Piece | Choice |
| --- | --- |
| Stack | Vite + React 19 + **Tailwind** + **shadcn/ui** (Base UI primitives) |
| Install | Official shadcn CLI for Vite; `components.json` at `apps/web` |
| Tokens | CSS variables for bg/fg/accent — match existing Navbe cockpit feel; avoid purple-on-white default if it fights current brand |
| First primitives | `Button`, `Badge`, `Sheet`, `Table`, `Tabs`, `Input`, `Select`, `Card` (only where interaction needs a container), `Separator` |
| Motion | Keep live-run CSS/framer-free first (`@keyframes` / Tailwind `animate-*`); add a motion lib only if XYFlow + CSS is too weak |

### Migration approach

1. Add Tailwind + shadcn scaffold; leave app runnable.
2. Replace shell nav + layout.
3. Runs table + StatusBadge + RunDetailSheet (sheet = shadcn Sheet).
4. Connectors / Workflows / Reports tabs & forms.
5. Delete orphan one-off CSS as components migrate.

**Craft rule:** page behavior unchanged; visual system only. Auto-open + animation land on the new shell, not a parallel UI.

### Files (indicative)

- `apps/web/package.json`, `vite.config.ts`, `src/index.css`, `components.json`
- `apps/web/src/components/ui/*` (generated shadcn)
- Page/components listed above

---

## Implementation order

1. **shadcn scaffold** — Tailwind + Base UI primitives + shell restyle (unblocks consistent Sheet/Badge for live UI).
2. **Auto-open on trigger** — SSE `run.started` → navigate + open run sheet; harden deep-link on load.
3. **DAG animation** — running pulse + edge motion wired to `dagStore` / step events.
4. **Agent result message** — `agent_message` on terminal publish; verify Cursor `pull_events` after a run.
5. **Migrate remaining pages** onto shared primitives (Connectors, Workflows, Reports) without behavior churn.
6. Smoke: `run_workflow` → UI animates → finish → `pull_events` shows `agent_message`.

---

## Done when

- Starting a workflow focuses the Control UI on that run’s sheet with an animated live DAG.
- Finishing a run publishes an agent-readable `agent_message`; a Cursor subscriber gets it via `pull_events` (and MCP notify if enabled).
- Control UI builds on shadcn Base UI primitives for shell + primary pages; status/duration/runs behavior from Sprint 11 still works.
- No second backend — UI remains a peer of the same daemon bus.
