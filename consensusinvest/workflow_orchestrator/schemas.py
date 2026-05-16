"""Pydantic schemas for Workflow API projection."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowQueryRequest(WorkflowModel):
    lookback_days: int = 30
    sources: list[str] = Field(default_factory=lambda: ["akshare", "tavily", "exa"])
    evidence_types: list[str] = Field(default_factory=lambda: ["financial_report", "company_news", "industry_news"])
    max_results: int = 50


class WorkflowOptionsRequest(WorkflowModel):
    stream: bool = True
    include_raw_payload: bool = False
    auto_run: bool = False


class WorkflowRunCreateRequest(WorkflowModel):
    ticker: str
    analysis_time: datetime
    workflow_config_id: str
    query: WorkflowQueryRequest = Field(default_factory=WorkflowQueryRequest)
    options: WorkflowOptionsRequest = Field(default_factory=WorkflowOptionsRequest)
    entity_id: str | None = None
    stock_code: str | None = None


class WorkflowRunCreateView(WorkflowModel):
    workflow_run_id: str
    status: str
    ticker: str
    analysis_time: str
    workflow_config_id: str
    created_at: str
    events_url: str
    snapshot_url: str
    failure_code: str | None = None
    failure_message: str | None = None


class WorkflowProgressView(WorkflowModel):
    raw_items_collected: int = 0
    evidence_items_normalized: int = 0
    evidence_items_structured: int = 0
    agent_arguments_completed: int = 0


class WorkflowLinksView(WorkflowModel):
    events: str
    snapshot: str
    trace: str
    evidence: str
    judgment: str


class WorkflowRunDetailView(WorkflowModel):
    workflow_run_id: str
    ticker: str
    status: str
    stage: str
    analysis_time: str
    workflow_config_id: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    progress: WorkflowProgressView
    links: WorkflowLinksView


class WorkflowRunListItemView(WorkflowModel):
    workflow_run_id: str
    ticker: str
    status: str
    analysis_time: str
    workflow_config_id: str
    created_at: str
    completed_at: str | None = None
    judgment_id: str | None = None
    final_signal: str | None = None
    confidence: float | None = None


class EvidenceItemSnapshotView(WorkflowModel):
    evidence_id: str
    raw_ref: str
    ticker: str | None = None
    source: str | None = None
    source_type: str | None = None
    evidence_type: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    publish_time: str | None = None
    fetched_at: str | None = None
    source_quality: float | None = None
    relevance: float | None = None
    freshness: float | None = None


class AgentRunSnapshotView(WorkflowModel):
    agent_run_id: str
    workflow_run_id: str
    agent_id: str
    role: str
    status: str
    started_at: str
    completed_at: str | None = None
    rounds: list[int] = Field(default_factory=list)


class AgentArgumentSnapshotView(WorkflowModel):
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
    created_at: str | None = None


class RoundSummarySnapshotView(WorkflowModel):
    round_summary_id: str
    workflow_run_id: str
    round: int
    summary: str
    participants: list[str] = Field(default_factory=list)
    agent_argument_ids: list[str] = Field(default_factory=list)
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    disputed_evidence_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None


class JudgmentSnapshotView(WorkflowModel):
    judgment_id: str
    workflow_run_id: str
    final_signal: str
    confidence: float
    time_horizon: str
    key_positive_evidence_ids: list[str] = Field(default_factory=list)
    key_negative_evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str
    risk_notes: list[str] = Field(default_factory=list)
    suggested_next_checks: list[str] = Field(default_factory=list)
    referenced_agent_argument_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: str | None = None


class JudgeToolCallSnapshotView(WorkflowModel):
    tool_call_id: str
    judgment_id: str
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output_summary: str
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None


class WorkflowSnapshotRunView(WorkflowModel):
    workflow_run_id: str
    ticker: str
    status: str
    stage: str
    failure_code: str | None = None
    failure_message: str | None = None


class WorkflowSnapshotView(WorkflowModel):
    workflow_run: WorkflowSnapshotRunView
    evidence_items: list[EvidenceItemSnapshotView] = Field(default_factory=list)
    agent_runs: list[AgentRunSnapshotView] = Field(default_factory=list)
    agent_arguments: list[AgentArgumentSnapshotView] = Field(default_factory=list)
    round_summaries: list[RoundSummarySnapshotView] = Field(default_factory=list)
    judgment: JudgmentSnapshotView | None = None
    judge_tool_calls: list[JudgeToolCallSnapshotView] = Field(default_factory=list)
    last_event_sequence: int
    events: list["WorkflowEventView"] | None = None


class TraceNodeView(WorkflowModel):
    node_type: Literal["judgment", "agent_argument", "evidence", "raw_item", "round_summary"]
    node_id: str
    title: str
    summary: str


class TraceEdgeView(WorkflowModel):
    from_node_id: str
    to_node_id: str
    edge_type: str


class WorkflowTraceView(WorkflowModel):
    workflow_run_id: str
    judgment_id: str | None = None
    trace_nodes: list[TraceNodeView]
    trace_edges: list[TraceEdgeView]


class WorkflowEventView(WorkflowModel):
    event_id: str
    workflow_run_id: str
    sequence: int
    event_type: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)
