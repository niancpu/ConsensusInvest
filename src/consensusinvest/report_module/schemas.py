"""Pydantic request/response schemas for the Report Module HTTP API.

These exactly mirror the field names and shapes documented in:

- docs/report_module/stock_research.md
- docs/report_module/market.md

The Report Module is a view layer. Outgoing payloads always carry a traceable
reference (`evidence_ids`, `market_snapshot_ids`, `entity_ids`, `workflow_run_id`,
`judgment_id`, or `report_run_id`) so downstream consumers can drill back.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    MISSING = "missing"
    PENDING_REFRESH = "pending_refresh"
    REFRESHING = "refreshing"
    STALE = "stale"
    FAILED = "failed"


class ReportMode(str, Enum):
    REPORT_GENERATION = "report_generation"
    WITH_WORKFLOW_TRACE = "with_workflow_trace"


class RefreshPolicy(str, Enum):
    NEVER = "never"
    MISSING = "missing"
    STALE = "stale"


class Signal(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class TraceableModel(BaseModel):
    """Models in this API forbid extra fields so contract drift is caught early."""

    model_config = ConfigDict(extra="forbid")


# -- Stocks: search ---------------------------------------------------------


class EvidenceMatch(TraceableModel):
    evidence_id: str
    title: str
    objective_summary: str
    published_at: str
    source_quality: float


class SearchMatch(TraceableModel):
    type: Literal["entity", "evidence", "entity_and_evidence"]
    score: float
    matched_fields: list[str]


class StockSearchHit(TraceableModel):
    stock_code: str
    ticker: str
    exchange: str
    name: str
    market: str
    entity_id: str
    aliases: list[str] = Field(default_factory=list)
    match: SearchMatch
    evidence_matches: list[EvidenceMatch] = Field(default_factory=list)


# -- Stocks: research aggregation view --------------------------------------


class KeyEvidence(TraceableModel):
    evidence_id: str
    title: str
    objective_summary: str
    source_quality: float
    relevance: float


class RiskItem(TraceableModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    source: str


class BenefitItem(TraceableModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    source: str


class ReportBody(TraceableModel):
    title: str
    summary: str
    key_evidence: list[KeyEvidence] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)


class ActionView(TraceableModel):
    label: str
    signal: Signal
    reason: str
    source: Literal["main_judgment_summary"]


class TraceRefs(TraceableModel):
    evidence_ids: list[str] = Field(default_factory=list)
    market_snapshot_ids: list[str] = Field(default_factory=list)
    workflow_run_id: str | None = None
    judgment_id: str | None = None


class StockLinks(TraceableModel):
    workflow_run: str | None = None
    trace: str | None = None
    judgment: str | None = None
    entity: str | None = None


class StockAnalysisView(TraceableModel):
    stock_code: str
    ticker: str
    stock_name: str
    entity_id: str
    workflow_run_id: str | None = None
    judgment_id: str | None = None
    report_run_id: str
    report_mode: ReportMode
    data_state: DataState
    action: ActionView | None = None
    report: ReportBody
    trace_refs: TraceRefs
    links: StockLinks
    updated_at: str


# -- Stocks: industry-details ----------------------------------------------


class IndustryLinks(TraceableModel):
    entity: str
    entity_relations: str


class IndustryDetailsView(TraceableModel):
    stock_code: str
    ticker: str
    industry_entity_id: str
    industry_name: str
    policy_support_level: Literal["low", "medium", "high"]
    policy_support_desc: str
    supply_demand_status: str
    competition_landscape: str
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    market_snapshot_ids: list[str] = Field(default_factory=list)
    links: IndustryLinks
    updated_at: str


# -- Stocks: event-impact-ranking ------------------------------------------


class EventImpactItem(TraceableModel):
    event_name: str
    impact_score: int
    impact_level: Literal["low", "medium", "high"]
    direction: Literal["positive", "neutral", "negative"] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    workflow_run_id: str | None = None
    judgment_id: str | None = None


class EventImpactRankingView(TraceableModel):
    stock_code: str
    ticker: str
    ranker: str
    items: list[EventImpactItem]
    updated_at: str


# -- Stocks: benefits-risks ------------------------------------------------


class BenefitsRisksView(TraceableModel):
    stock_code: str
    ticker: str
    workflow_run_id: str | None = None
    report_run_id: str
    benefits: list[BenefitItem] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    updated_at: str


# -- Market: index-overview ------------------------------------------------


class IndexQuote(TraceableModel):
    name: str
    code: str
    value: float
    change_rate: float
    is_up: bool
    snapshot_id: str


class MarketSentiment(TraceableModel):
    label: str
    score: int
    source: Literal["market_snapshot_projection"]
    snapshot_ids: list[str] = Field(default_factory=list)


class IndexOverview(TraceableModel):
    indices: list[IndexQuote]
    market_sentiment: MarketSentiment
    data_state: DataState
    refresh_task_id: str | None = None
    updated_at: str


# -- Market: stocks --------------------------------------------------------


class MarketStockRow(TraceableModel):
    stock_code: str
    ticker: str
    name: str
    price: float
    change_rate: float
    is_up: bool
    view_score: int
    view_label: str
    entity_id: str
    snapshot_id: str


class MarketStocksPagination(TraceableModel):
    page: int
    page_size: int
    total: int


class MarketStocksList(TraceableModel):
    list: list[MarketStockRow]  # noqa: A003 — field name fixed by API contract
    pagination: MarketStocksPagination
    data_state: DataState
    refresh_task_id: str | None = None


# -- Market: concept-radar -------------------------------------------------


class ConceptRadarItem(TraceableModel):
    concept_name: str
    entity_id: str
    status: str
    heat_score: int
    trend: Literal["warming", "cooling", "flat"]
    snapshot_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


# -- Market: warnings ------------------------------------------------------


class MarketWarning(TraceableModel):
    warning_id: str
    time: str
    title: str
    content: str
    severity: Literal["info", "notice", "alert"]
    related_stock_codes: list[str] = Field(default_factory=list)
    related_entity_ids: list[str] = Field(default_factory=list)
    snapshot_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
