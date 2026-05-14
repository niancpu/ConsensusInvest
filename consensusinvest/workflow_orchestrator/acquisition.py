"""Evidence gap to SearchTask conversion owned by Workflow Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from consensusinvest.agent_swarm.models import EvidenceGap
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent import SearchAgentPool
from consensusinvest.search_agent.models import (
    SearchBudget,
    SearchCallback,
    SearchConstraints,
    SearchExpansionPolicy,
    SearchScope,
    SearchTarget,
    SearchTask,
)

from .models import WorkflowQuery


@dataclass(frozen=True, slots=True)
class EvidenceGapFillTarget:
    ticker: str
    stock_code: str | None = None
    entity_id: str | None = None
    keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "keywords", tuple(self.keywords))


@dataclass(frozen=True, slots=True)
class EvidenceGapFillPolicy:
    source_allowlist: tuple[str, ...]
    max_retry_rounds: int = 2
    max_retry_per_gap_type: int = 1
    default_lookback_days: int = 30
    max_results: int = 50
    max_provider_calls: int = 20
    max_runtime_ms: int = 60000
    expansion_allowed: bool = True
    expansion_max_depth: int = 1
    expansion_allowed_actions: tuple[str, ...] = (
        "fetch_original_url",
        "follow_official_source",
        "provider_pagination",
        "same_event_cross_source",
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_allowlist", tuple(self.source_allowlist))
        object.__setattr__(self, "expansion_allowed_actions", tuple(self.expansion_allowed_actions))


@dataclass(frozen=True, slots=True)
class EvidenceGapFillRequest:
    workflow_run_id: str
    gap: EvidenceGap
    target: EvidenceGapFillTarget
    policy: EvidenceGapFillPolicy


class EvidenceAcquisitionService:
    """Builds and submits constrained SearchTasks for workflow-owned gaps."""

    def __init__(self, search_pool: SearchAgentPool | None = None) -> None:
        self.search_pool = search_pool

    def build_search_task(
        self,
        envelope: InternalCallEnvelope,
        request: EvidenceGapFillRequest,
    ) -> SearchTask:
        if not envelope.workflow_run_id or envelope.workflow_run_id != request.workflow_run_id:
            raise ValueError("workflow_run_id must be present and match gap fill request")
        if not request.gap.gap_type:
            raise ValueError("gap_type is required")
        if not request.policy.source_allowlist:
            raise ValueError("source_allowlist must not be empty")

        suggested = request.gap.suggested_search
        suggested_keywords = suggested.keywords if suggested is not None else ()
        evidence_types = suggested.evidence_types if suggested is not None else ()
        lookback_days = suggested.lookback_days if suggested is not None else None
        target_keywords = _dedupe([*request.target.keywords, *suggested_keywords])

        return SearchTask(
            task_type="workflow_gap_fill",
            target=SearchTarget(
                query=" ".join(target_keywords) or request.target.ticker,
                ticker=request.target.ticker,
                stock_code=request.target.stock_code,
                entity_id=request.target.entity_id,
                keywords=tuple(target_keywords),
                metadata={"gap_type": request.gap.gap_type},
            ),
            scope=SearchScope(
                sources=request.policy.source_allowlist,
                evidence_types=evidence_types,
                lookback_days=lookback_days or request.policy.default_lookback_days,
                max_results=request.policy.max_results,
            ),
            constraints=SearchConstraints(
                expansion_policy=SearchExpansionPolicy(
                    allowed=request.policy.expansion_allowed,
                    allowed_actions=request.policy.expansion_allowed_actions,
                    max_depth=request.policy.expansion_max_depth,
                ),
                budget=SearchBudget(
                    max_provider_calls=request.policy.max_provider_calls,
                    max_runtime_ms=request.policy.max_runtime_ms,
                ),
                metadata={"gap_type": request.gap.gap_type},
            ),
            callback=SearchCallback(
                ingest_target="evidence_store",
                workflow_run_id=envelope.workflow_run_id,
                metadata={"event_name": "search.item_ingested"},
            ),
            idempotency_key=envelope.idempotency_key,
            metadata={"gap_description": request.gap.description},
        )

    def request_gap_fill(
        self,
        envelope: InternalCallEnvelope,
        request: EvidenceGapFillRequest,
    ) -> Any:
        if self.search_pool is None:
            raise RuntimeError("search_pool is required to submit gap fill tasks")
        return self.search_pool.submit(envelope, self.build_search_task(envelope, request))


def build_gap_fill_request(
    *,
    workflow_run_id: str,
    gap: EvidenceGap,
    ticker: str,
    stock_code: str | None,
    entity_id: str | None,
    query: WorkflowQuery,
) -> EvidenceGapFillRequest:
    return EvidenceGapFillRequest(
        workflow_run_id=workflow_run_id,
        gap=gap,
        target=EvidenceGapFillTarget(
            ticker=ticker,
            stock_code=stock_code,
            entity_id=entity_id,
            keywords=(ticker,),
        ),
        policy=EvidenceGapFillPolicy(
            source_allowlist=query.sources,
            default_lookback_days=query.lookback_days,
            max_results=query.max_results,
        ),
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


__all__ = [
    "EvidenceAcquisitionService",
    "EvidenceGapFillPolicy",
    "EvidenceGapFillRequest",
    "EvidenceGapFillTarget",
    "build_gap_fill_request",
]
