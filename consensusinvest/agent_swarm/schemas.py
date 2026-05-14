"""Pydantic schemas for Agent/Judgment Web API projection."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TraceableModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRunView(TraceableModel):
    agent_run_id: str
    workflow_run_id: str
    agent_id: str
    role: str
    status: Literal["queued", "running", "partial_completed", "completed", "failed", "cancelled"]
    started_at: str
    completed_at: str | None = None
    rounds: list[int] = Field(default_factory=list)


class AgentArgumentView(TraceableModel):
    agent_argument_id: str
    agent_run_id: str
    workflow_run_id: str
    agent_id: str
    role: str
    round: int
    argument: str
    confidence: float
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    counter_evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    role_output: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class EvidenceReferenceView(TraceableModel):
    reference_id: str
    source_type: str
    source_id: str
    evidence_id: str
    reference_role: str
    round: int | None = None


class RoundSummaryView(TraceableModel):
    round_summary_id: str
    workflow_run_id: str
    round: int
    summary: str
    participants: list[str] = Field(default_factory=list)
    agent_argument_ids: list[str] = Field(default_factory=list)
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    disputed_evidence_ids: list[str] = Field(default_factory=list)
    created_at: str


class JudgmentLinks(TraceableModel):
    references: str
    trace: str


class JudgmentView(TraceableModel):
    judgment_id: str
    workflow_run_id: str
    final_signal: Literal["bullish", "neutral", "bearish"]
    confidence: float
    time_horizon: str
    key_positive_evidence_ids: list[str] = Field(default_factory=list)
    key_negative_evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str
    risk_notes: list[str] = Field(default_factory=list)
    suggested_next_checks: list[str] = Field(default_factory=list)
    referenced_agent_argument_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    tool_call_count: int
    created_at: str
    links: JudgmentLinks


class JudgeToolCallView(TraceableModel):
    tool_call_id: str
    judgment_id: str
    tool_name: str
    input: dict[str, Any]
    output_summary: str
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    used_for: str | None = None
    created_at: str
