"""MCP tool: list_analysis_templates affordable for a destination."""

from __future__ import annotations

from navbe_core.agent import WorkflowAgent
from pydantic import BaseModel, Field

from navbe_mcp.registry import register

RETAILER_TEMPLATE = {
    "id": "retailer_token_cost_daily",
    "name": "Tokens & cost per retailer per day",
    "description": (
        "Aggregates prompt/completion tokens and cost from Langfuse traces tagged retailer:[id]"
    ),
    "min_schema_version": 1,
    "query_example": (
        "SELECT * FROM mart_retailer_token_cost_daily ORDER BY date DESC, total_cost DESC LIMIT 20"
    ),
}


class ListAnalysisTemplatesResult(BaseModel):
    """Templates available for the given destination."""

    templates: list[dict] = Field(default_factory=list)
    next_step: str


def _list_analysis_templates(agent: WorkflowAgent, user_id: str, destination_id: str) -> dict:
    """Return analysis templates the destination can afford."""
    dest = agent.repo.get_destination(destination_id, user_id)
    if dest is None:
        return {
            "error": f"Destination not found: {destination_id}",
            "templates": [],
            "next_step": "call list_destinations",
        }

    templates: list[dict] = []
    if dest.type == "duckdb":
        templates.append(dict(RETAILER_TEMPLATE))

    return ListAnalysisTemplatesResult(
        templates=templates,
        next_step="use query_destination with the query_example to run the template",
    ).model_dump()


register(
    name="list_analysis_templates",
    fn=_list_analysis_templates,
    description=(
        "List analysis templates affordable for a destination "
        "(e.g. retailer token/cost daily for DuckDB)."
    ),
    parameters={
        "destination_id": {
            "type": "string",
            "description": "Destination to check template compatibility for",
        }
    },
)
