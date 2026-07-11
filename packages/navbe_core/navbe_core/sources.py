# Knowledge base of known upstream data sources. Each entry captures what a
# source *is* (entities, aliases an LLM client's free-text hint might use)
# and how Navbe recommends ingesting it (DAG shape, destination, dedup
# strategy) — the pattern to copy when adding a new source: one dict entry,
# no new code paths.
SOURCES: dict[str, dict] = {
    "langfuse": {
        "label": "Langfuse",
        "aliases": [
            "langfuse",
            "trace",
            "traces",
            "observation",
            "observations",
            "llm trace",
            "llm traces",
            "llm observability",
            "llm monitoring",
        ],
        "entities": ["traces", "observations"],
        "connector_type": "langfuse",
        "recommended_destination_type": "duckdb",
        "dedup_strategy": (
            "Incremental append, deduplicated by trace/observation id — rows already "
            "present are updated in place, nothing is re-inserted or duplicated on re-run."
        ),
        "graph": {
            "entry": "fetch_traces",
            "nodes": ["fetch_traces", "write_traces", "refresh_retailer_mart"],
            "edges": [
                ["fetch_traces", "write_traces"],
                ["write_traces", "refresh_retailer_mart"],
            ],
        },
        "default_input": {"limit": 50, "include_observations": True},
    },
}


def match_source(hint: str) -> str | None:
    hint = hint.lower()
    for key, meta in SOURCES.items():
        if any(alias in hint for alias in meta["aliases"]):
            return key
    return None


def render_markdown(
    source_key: str, connector_name: str | None, destination_name: str | None
) -> str:
    meta = SOURCES[source_key]
    steps_md = "\n".join(f"{i}. `{node}`" for i, node in enumerate(meta["graph"]["nodes"], start=1))
    source_line = (
        connector_name
        or f"*(no {meta['label']} connector yet — create one with `create_connector`)*"
    )
    destination_line = destination_name or (
        f"*(no {meta['recommended_destination_type']} destination yet — create one with `create_destination`)*"
    )

    return (
        f"## Suggested workflow: monitor {meta['label']} {'/'.join(meta['entities'])}\n\n"
        f"**Source:** {source_line}\n\n"
        f"**Steps:**\n{steps_md}\n\n"
        f"**Destination:** {destination_line}\n\n"
        f"**Data engineering practices:** {meta['dedup_strategy']}\n\n"
        'Reply with a schedule (e.g. "every monday at 9am") to confirm and run it.'
    )
