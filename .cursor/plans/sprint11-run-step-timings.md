# Sprint 11 — Run & step execution timings

Store wall-clock duration **per run** and **per step** so MCP and the Control UI can answer *“how long did this sync take?”* and *“which step is slow?”* without scraping giant `output` JSON blobs.

**User pain:** *“I need per-run and per-step time in ms or seconds.”*

---

## Defaults (locked)

| Knob | Choice | Why |
| --- | --- | --- |
| Unit stored | **`duration_ms`** (integer) | Precise; UI formats `1.2s` / `840ms` |
| Run total | Column `workflow_runs.duration_ms` | Cheap list/sort; no JSON parse |
| Per step | Table `workflow_run_steps` | Queryable; survives huge/truncated output |
| Also in events/`steps` array | Mirror `duration_ms` on each step entry | Live SSE + existing RunDetail consumers |
| Clock | `time.perf_counter()` around each LangGraph node | Monotonic; not wall-clock skew |
| Mid-step live ETA | Out of scope | Current `stream_mode="updates"` fires after node finishes — duration is still correct |
| Backfill old runs | Best-effort from `started_at`/`completed_at` only for **run** total; steps stay null | Old runs have no step boundary clocks |

**Out of scope:** Prometheus/OTLP export; percentile aggregates; wall-clock NTP sync; changing LangGraph to `astream_events` for true mid-step “running” (keep existing ponytail).

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| Run has `started_at` / `completed_at` only | Duration not persisted; clients must subtract |
| Steps are `{id, status}` in `output.steps` | No start/end or duration |
| `run.step` events fire after node completes | “started” is sequencing only — fine once we stamp `duration_ms` at success |
| Huge `output` JSON | Timings must not depend solely on parsing output |

---

## Goal

1. Every finished run stores `duration_ms` (= completed − started, or sum of steps if preferred — **prefer wall clock of the run**).
2. Every finished/failed step stores `started_at`, `completed_at`, `duration_ms`, `status`.
3. `get_run` / `list_runs` / bus events expose timings.
4. Control UI: Runs table shows run duration; run detail shows per-step duration.

---

## Domain model

```text
WorkflowRun (+ duration_ms INTEGER NULL)

WorkflowRunStep  (new)
────────────────
id, run_id FK → workflow_runs
step_id        # node name e.g. fetch_traces
attempt        # default 1
status         # succeeded | failed | skipped | cancelled
started_at, completed_at
duration_ms    # integer; null if still running / unknown
```

Migration: `create_all` + additive `ALTER TABLE workflow_runs ADD COLUMN duration_ms` + create `workflow_run_steps` if missing (same pattern as Sprint 10 env migrate).

On run complete/cancel/fail: set `workflow_runs.duration_ms` from timestamps (or `perf_counter` span of the execute loop).

On each LangGraph update (step finished): insert/update step row; append to `steps_done`:

```json
{ "id": "fetch_traces", "status": "succeeded", "duration_ms": 1234 }
```

Event payload extras: `duration_ms` on `run.step` / terminal `run.succeeded`.

---

## Surfaces

### Core / agent

- [`agent.py`](packages/navbe_core/navbe_core/agent.py) execute loop: `t0 = perf_counter()` per step; on finish write repo + `steps_done`.
- [`repository.py`](packages/navbe_core/navbe_core/repository.py): `upsert_run_step`, `list_run_steps`, set `duration_ms` in `complete_run` / cancel / fail helpers.
- [`models.py`](packages/navbe_core/navbe_core/models.py): `WorkflowRunStepModel` + migrate.

### API / MCP

- `list_runs` / `get_run` / hub run detail: include `duration_ms` and `steps: [{id, status, duration_ms, started_at?, completed_at?}]`.
- Prefer steps from `workflow_run_steps` over `output.steps` when present.

### Control UI

- [`RunsPage.tsx`](apps/web/src/pages/RunsPage.tsx): Duration column (`840ms` / `12.4s`).
- [`RunDetailSheet.tsx`](apps/web/src/components/RunDetailSheet.tsx) / DAG step list: show step `duration_ms`.
- [`RunMetrics.tsx`](apps/web/src/components/RunMetrics.tsx): include run `duration_ms` when available.

### Docs

- Short note in [`AGENTS.md`](AGENTS.md) Run model / glossary: timings are `duration_ms`.

---

## Implementation order

1. Schema: `duration_ms` on runs + `workflow_run_steps` table.
2. Repo helpers + wire agent execute loop.
3. Serialize in API / MCP get_run / list_runs.
4. Control UI run list + detail.
5. Smoke: run `langfuse_daily` (or any graph) → assert run + each step have `duration_ms > 0`.

---

## Done when

- New runs persist `duration_ms` on the run row.
- Each step has a `workflow_run_steps` row with `duration_ms`.
- Runs UI shows total duration; run detail shows per-step duration.
- MCP/API return the same numbers (single source of truth = control-plane tables).
