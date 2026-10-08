from typing import Any, Literal

from pydantic import BaseModel, Field


class KnowledgeResult(BaseModel):
    status: Literal["success", "empty", "error"]
    summary: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    error: str | None = None


class OpsResult(BaseModel):
    status: Literal["success", "empty", "error"]
    facts: list[dict[str, Any]] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    freshness: str = "live"
    error: str | None = None


class DiagnosisResult(BaseModel):
    status: Literal["success", "empty", "error"]
    findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    error: str | None = None


class SupervisorResult(BaseModel):
    status: Literal["success", "error"]
    answer: str
    used_agents: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
