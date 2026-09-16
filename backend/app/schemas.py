"""Request and response contracts.

Every endpoint's shape is declared here, which is what makes the OpenAPI docs at
/docs a usable handoff artifact rather than a list of untyped dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------ errors
class ErrorDetail(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="What went wrong, in plain language.")
    hint: str | None = Field(None, description="The most likely fix.")
    trace_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------- sessions
class SessionCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    user_id: str = Field("local-evaluator", max_length=120)
    user_metadata: dict[str, Any] = Field(default_factory=dict)


class SessionOut(BaseModel):
    id: str
    title: str
    user_id: str
    provider: str | None = None
    model: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


# ---------------------------------------------------------------- messages
class Citation(BaseModel):
    marker: str
    chunk_id: str
    source_id: str
    title: str
    guest: str | None = None
    episode_url: str | None = None
    timestamp: str | None = None
    heading: str | None = None
    score: float
    retrieved_by: str
    excerpt: str


class ArtifactOut(BaseModel):
    id: str | None = None
    kind: Literal["markdown", "html"]
    title: str
    content: str
    sanitizer_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    skill: str | None = None
    grounding: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    token_usage: dict[str, int] = Field(default_factory=dict)
    created_at: datetime


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = Field(
        None, description="Omit to start a new session; the response returns its id."
    )
    user_id: str = "local-evaluator"
    force_skill: Literal["grounded_qa", "ship30_essay", "artifact"] | None = Field(
        None, description="Bypass the router. Used by the UI's skill buttons and evals."
    )

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message cannot be blank")
        return v.strip()


class ChatResponse(BaseModel):
    session_id: str
    session_title: str
    message: MessageOut
    artifact: ArtifactOut | None = None
    essay_report: dict[str, Any] | None = None
    route: dict[str, Any] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)
    trace_id: str


# ------------------------------------------------------------------ system
class ProviderInfo(BaseModel):
    chat: dict[str, Any]
    fallback: dict[str, Any] | None = None
    embedding: dict[str, Any]
    agent_runtime: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    checks: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    top_k: int = Field(8, ge=1, le=20)


class SearchResponse(BaseModel):
    query: str
    sufficiency: str
    reason: str
    degraded: bool
    results: list[Citation]
