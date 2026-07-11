"""Pydantic models for MVP B trace replay."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Auth for the target API call."""

    type: Literal["none", "bearer", "api_key", "basic"]
    token: str | None = None
    header: str = "Authorization"
    username: str | None = None
    password: str | None = None


class ReplayRequest(BaseModel):
    """MCP / API input for replay_trace_to_api."""

    trace_id: str
    connection_id: str
    api_url: str
    method: Literal["GET", "POST", "PUT", "PATCH"] = "POST"
    auth: AuthConfig
    input_mapping: dict[str, str] = Field(default_factory=dict)
    destination_id: str | None = None
    save_as_workflow: bool = False


class DiffEntry(BaseModel):
    """One path where expected and actual differ."""

    path: str
    expected: Any
    actual: Any
    match: bool = False


class ExperimentMessageDiff(BaseModel):
    """Agent message text comparison — the main experiment signal."""

    index: int
    expected: str | None = None
    actual: str | None = None
    match: bool = False


class CompareResult(BaseModel):
    """Structured diff between trace output and API response."""

    identical: bool
    diff_count: int
    diffs: list[DiffEntry]
    experiment_messages: list[ExperimentMessageDiff] = Field(default_factory=list)
    messages_identical: bool = True


class ReplayResult(BaseModel):
    """MCP / API response for a completed replay."""

    replay_id: str
    trace_id: str
    status_code: int
    latency_ms: float
    compare: CompareResult
    workflow_id: str | None = None
    live_url: str | None = None
    next_step: str
