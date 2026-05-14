"""Workflow Orchestrator contract and storage models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from consensusinvest.agent_swarm.models import EvidenceGap

WorkflowStatus = Literal["queued", "running", "completed", "failed", "insufficient_evidence", "cancelled"]
WorkflowStage = Literal["queued", "search", "evidence_selection", "debate", "judge", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class WorkflowQuery:
    lookback_days: int = 30
    sources: tuple[str, ...] = ("akshare", "tushare", "tavily", "exa")
    evidence_types: tuple[str, ...] = ("financial_report", "company_news", "industry_news")
    max_results: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "evidence_types", tuple(self.evidence_types))


@dataclass(frozen=True, slots=True)
class WorkflowOptions:
    stream: bool = True
    include_raw_payload: bool = False
    auto_run: bool = True


@dataclass(frozen=True, slots=True)
class WorkflowRunCreate:
    ticker: str
    analysis_time: datetime
    workflow_config_id: str
    query: WorkflowQuery = field(default_factory=WorkflowQuery)
    options: WorkflowOptions = field(default_factory=WorkflowOptions)
    entity_id: str | None = None
    stock_code: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowProgress:
    raw_items_collected: int = 0
    evidence_items_normalized: int = 0
    evidence_items_structured: int = 0
    agent_arguments_completed: int = 0


@dataclass(frozen=True, slots=True)
class WorkflowRunRecord:
    workflow_run_id: str
    correlation_id: str
    ticker: str
    analysis_time: datetime
    workflow_config_id: str
    status: WorkflowStatus
    stage: WorkflowStage
    query: WorkflowQuery
    options: WorkflowOptions
    entity_id: str | None
    stock_code: str | None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    judgment_id: str | None = None
    final_signal: str | None = None
    confidence: float | None = None
    progress: WorkflowProgress = field(default_factory=WorkflowProgress)
    failure_code: str | None = None
    failure_message: str | None = None
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    search_task_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))
        object.__setattr__(self, "search_task_ids", tuple(self.search_task_ids))


@dataclass(frozen=True, slots=True)
class WorkflowEventRecord:
    event_id: str
    workflow_run_id: str
    sequence: int
    event_type: str
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowTraceNode:
    node_type: str
    node_id: str
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class WorkflowTraceEdge:
    from_node_id: str
    to_node_id: str
    edge_type: str
