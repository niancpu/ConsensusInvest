"""Runtime dependency wiring for the FastAPI application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from consensusinvest.agent_swarm import (
    AgentSwarmRuntime,
    JudgeRuntime,
    build_agent_llm_provider_from_env,
)
from consensusinvest.agent_swarm.repository import (
    InMemoryAgentSwarmRepository,
    seed_demo_repository,
)
from consensusinvest.entities import InMemoryEntityRepository, seed_entity_repository
from consensusinvest.evidence_store import EvidenceStructureDraft, FakeEvidenceStoreClient
from consensusinvest.runtime.env import load_local_env
from consensusinvest.runtime.models import InternalCallEnvelope
from consensusinvest.search_agent import SearchAgentPool, build_real_search_providers_from_env
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget
from consensusinvest.workflow_orchestrator import (
    EvidenceAcquisitionService,
    InMemoryWorkflowRepository,
    WorkflowOrchestrator,
)


@dataclass(slots=True)
class AppRuntime:
    evidence_store: FakeEvidenceStoreClient
    entity_repository: InMemoryEntityRepository
    agent_repository: InMemoryAgentSwarmRepository
    workflow_repository: InMemoryWorkflowRepository
    agent_swarm: AgentSwarmRuntime
    judge: JudgeRuntime
    search_pool: SearchAgentPool
    workflow_service: WorkflowOrchestrator


def build_runtime(*, seed_demo_data: bool = False) -> AppRuntime:
    load_local_env()
    llm_provider = build_agent_llm_provider_from_env()
    evidence_store = FakeEvidenceStoreClient()
    entity_repository = seed_entity_repository()
    if seed_demo_data:
        _seed_demo_evidence(evidence_store)
    agent_repository = seed_demo_repository() if seed_demo_data else InMemoryAgentSwarmRepository()
    workflow_repository = InMemoryWorkflowRepository()
    agent_swarm = AgentSwarmRuntime(
        evidence_store=evidence_store,
        repository=agent_repository,
        llm_provider=llm_provider,
    )
    judge = JudgeRuntime(
        evidence_store=evidence_store,
        repository=agent_repository,
        llm_provider=llm_provider,
    )
    search_pool = SearchAgentPool(
        providers=build_real_search_providers_from_env(),
        evidence_store=evidence_store,
    )
    workflow_service = WorkflowOrchestrator(
        repository=workflow_repository,
        evidence_store=evidence_store,
        agent_swarm=agent_swarm,
        judge=judge,
        acquisition=EvidenceAcquisitionService(search_pool=search_pool),
    )
    return AppRuntime(
        evidence_store=evidence_store,
        entity_repository=entity_repository,
        agent_repository=agent_repository,
        workflow_repository=workflow_repository,
        agent_swarm=agent_swarm,
        judge=judge,
        search_pool=search_pool,
        workflow_service=workflow_service,
    )


def _seed_demo_evidence(evidence_store: FakeEvidenceStoreClient) -> None:
    envelope = InternalCallEnvelope(
        request_id="req_runtime_seed",
        correlation_id="corr_runtime_seed",
        workflow_run_id=None,
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="runtime_seed",
        idempotency_key="runtime_seed_evidence",
    )
    result = evidence_store.ingest_search_result(
        envelope,
        SearchResultPackage(
            task_id="st_runtime_seed_001",
            worker_id="worker_runtime_seed",
            source="tavily",
            source_type="web_news",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("BYD",),
            ),
            items=(
                {
                    "external_id": "runtime_seed_news_001",
                    "title": "BYD operating update",
                    "url": "https://example.com/runtime-seed/001",
                    "content": "BYD published a factual operating update.",
                    "content_preview": "BYD operating update.",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "fetched_at": "2026-05-13T09:00:00+00:00",
                    "source_quality_hint": 0.82,
                    "relevance": 0.9,
                    "raw_payload": {"provider_response": {"id": "runtime_seed_news_001"}},
                },
            ),
            completed_at="2026-05-13T09:00:00+00:00",
            metadata={"evidence_type": "company_news"},
        ),
    )
    if result.created_evidence_ids:
        evidence_store.save_structure(
            envelope,
            EvidenceStructureDraft(
                evidence_id=result.created_evidence_ids[0],
                objective_summary="BYD published a factual operating update.",
                claims=[
                    {
                        "claim": "BYD published an operating update.",
                        "evidence_span": "published a factual operating update",
                        "claim_type": "reported_fact",
                    }
                ],
                structuring_confidence=0.8,
                created_by_agent_id="runtime_seed_structurer",
            ),
        )


__all__ = ["AppRuntime", "build_runtime"]
