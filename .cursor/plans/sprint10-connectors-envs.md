# Sprint 10 — Connectors hub: Sources + Destinations (email is a destination)

Replace **Settings** with a top-level **Connectors** page. Humans and MCP manage **Sources** (Langfuse + env credentials) and **Destinations** (DuckDB / SQLite / **email**). Email is **not** its own menu category — it is a destination type. Workflows keep per-env source bindings and per-step overrides.

**User pain:** *“I need staging vs prod source keys, destinations including email in one place — not a Settings island.”*

---

## Defaults (locked)

| Knob | Choice | Why |
| --- | --- | --- |
| Top nav | `Runs` · `Workflows` · `Reports` · **Connectors** | Settings removed |
| Connectors tabs | **Sources** \| **Destinations** only | No Email category |
| Email | Destination `type=email` (Resend/SMTP) | User: email is a destination |
| Source envs | `staging` \| `testing` \| `prod` + custom; Fernet secrets | Per-env credentials |
| Workflow default | `input.connector_id` + `input.connector_env` | Sprint 9 compat |
| Per-step override | `graph.node_config[step_id]` | Instantiation configs |
| Visual IR edit | Out of scope | MCP + Connectors UI author |

**Out of scope:** New source plugins (folder/HTTP) beyond open config JSON; destination env packs (DuckDB staging/prod); DAG drag-bind; Settings page.

---

## Diagnosis (current state)

| Symptom | Root cause |
| --- | --- |
| Settings owns catalog + email | Sprint 8 folded Integrations into Settings |
| Flat Langfuse credentials | `ConnectorModel` host/keys plaintext, no envs |
| No MCP connector update/delete | create/list only |
| One connector for whole graph | No `node_config` |
| Email feels like “settings” | Separate Settings section, not a destination |

---

## Goal

1. Top nav **Connectors**; Settings gone; `?page=settings` → `?page=connectors`.
2. Sources: env CRUD + test; MCP CRUD.
3. Destinations: DuckDB/SQLite **and** email destination card (configure Resend/SMTP, report actions).
4. Workflow default env + per-step `node_config`.
5. Legacy Langfuse rows migrate to `prod` env.

---

## Domain model

### Sources

```text
Connector                  ConnectorEnvironment
─────────                  ────────────────────
id, user_id, type, name    env_key, public_config, secrets_enc,
status                     is_default, status
```

### Destinations

Existing `DestinationModel`; types: `duckdb` | `sqlite` | **`email`**.

Email destination `config`: non-secrets (`provider`, `from_addr`); secrets stay in Fernet email store (reuse today’s encrypt path — one source of truth).

### Workflow IR

```json
{
  "input": {
    "connector_id": "c-langfuse",
    "connector_env": "prod",
    "destination_id": "d-duck"
  },
  "graph": {
    "entry": "fetch_traces",
    "nodes": ["fetch_traces", "write_traces"],
    "edges": [["fetch_traces", "write_traces"]],
    "node_config": {
      "fetch_traces": {
        "connector_id": "c-langfuse",
        "env": "staging",
        "config": { "limit": 10 }
      }
    }
  }
}
```

Resolve: step `node_config` → workflow `input` → connector `is_default` env.

---

## Frontend

- `ConnectorsPage` — tabs Sources | Destinations
- `SourcesPanel` — env chips, drawer, test
- `DestinationsPanel` — all destination types; email card hosts former Settings email UI
- Delete `SettingsPage`; App page `connectors`; Reports link to Destinations

Deep link: `?page=connectors&tab=destinations&type=email` for email focus.

---

## Backend / MCP

- Source: env table, migrate, MCP CRUD, `set_workflow_step_connector`
- Email: `configure_resend` / `configure_email` upsert destination `type=email`; settings routes alias one sprint
- `ui_url`: sources → `tab=sources`; email tools → `tab=destinations&type=email`

---

## Docs

Rewrite this file + [`AGENTS.md`](../AGENTS.md): Connectors hub; Email = destination type; no Settings / no Email category.

---

## Done signal

1. Nav: Connectors only (no Settings).
2. Tabs: Sources | Destinations only.
3. Email configured as a destination under Destinations.
4. Source envs + per-step bindings work via MCP/UI.
5. AGENTS.md + this plan match the IA.
