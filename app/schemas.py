from typing import Literal
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="demo-user", min_length=1, max_length=100)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)
    request_id: str | None = Field(default=None, min_length=36, max_length=36)
    execution_mode: Literal["multi", "single"] = "multi"
    bypass_cache: bool = False


class ContextInfo(BaseModel):
    max_input_tokens: int
    estimated_query_tokens: int = 0
    estimated_summary_tokens: int = 0
    estimated_recent_tokens: int = 0
    window_message_count: int = 0
    summarized_message_count: int = 0
    truncated_message_count: int = 0
    context_fingerprint: str = ""


class Citation(BaseModel):
    document_id: int | None = None
    title: str
    chunk_id: int | None = None
    source_uri: str | None = None
    score: float | None = None


class ExternalEvidence(BaseModel):
    source: str
    tool: str
    status: Literal["success", "empty", "unavailable", "error"]
    reference: str | None = None
    summary: str = ""
    latency_ms: int | None = None
    error: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    trace_id: str
    intent: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    cached: bool = False
    selected_path: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    model_info: list[dict] = Field(default_factory=list)
    context_info: ContextInfo | None = None
    memory: dict = Field(default_factory=dict)
    external_evidence: list[ExternalEvidence] = Field(default_factory=list)
    evidence_quality: dict = Field(default_factory=dict)


class SessionRenameRequest(BaseModel):
    user_id: str | None = Field(default=None, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)


class RouterDecision(BaseModel):
    intent: Literal["knowledge", "database", "ops_tool", "mixed", "direct"]
    reason: str
    service_name: str | None = None


class RouteDecisionV2(BaseModel):
    intent: Literal["knowledge", "database", "ops_tool", "mixed", "diagnosis", "direct"]
    complexity: Literal["simple", "complex"] = "simple"
    risk: Literal["low", "medium", "high"] = "low"
    service_name: str | None = None
    reason: str
    confidence: float = Field(ge=0, le=1)
    ops_action: Literal["service_status", "deployments", "incidents", "tickets"] | None = None
