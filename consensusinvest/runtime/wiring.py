"""Runtime dependency wiring for the FastAPI application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import TypeAlias

from consensusinvest.agent_swarm import (
    AgentSwarmRuntime,
    JudgeRuntime,
    SQLiteAgentSwarmRepository,
    build_agent_llm_provider_from_env,
)
from consensusinvest.agent_swarm.repository import (
    InMemoryAgentSwarmRepository,
    seed_demo_repository,
)
from consensusinvest.entities import (
    InMemoryEntityRepository,
    SQLiteEntityRepository,
    seed_entity_repository,
)
from consensusinvest.evidence_store import (
    EvidenceStoreClient,
    EvidenceStructureDraft,
    InMemoryEvidenceStoreClient,
    SQLiteEvidenceStoreClient,
)
from consensusinvest.report_module.repository import SQLiteReportRunRepository
from consensusinvest.runtime.env import load_local_env
from consensusinvest.runtime.models import InternalCallEnvelope
from consensusinvest.runtime.repository import SQLiteRuntimeEventRepository
from consensusinvest.search_agent import (
    SQLiteSearchTaskRepository,
    SearchAgentPool,
    build_real_search_providers_from_env,
)
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget
from consensusinvest.workflow_orchestrator import (
    EvidenceAcquisitionService,
    InMemoryWorkflowRepository,
    SQLiteWorkflowRepository,
    WorkflowOrchestrator,
)


AgentRepository: TypeAlias = InMemoryAgentSwarmRepository | SQLiteAgentSwarmRepository
WorkflowRepository: TypeAlias = InMemoryWorkflowRepository | SQLiteWorkflowRepository
EntityRepository: TypeAlias = InMemoryEntityRepository | SQLiteEntityRepository
ReportRepository: TypeAlias = SQLiteReportRunRepository | None
RuntimeEventRepository: TypeAlias = SQLiteRuntimeEventRepository | None
RuntimeDbPaths: TypeAlias = tuple[str, str, str, str, str, str]


@dataclass(slots=True)
class AppRuntime:
    evidence_store: EvidenceStoreClient
    entity_repository: EntityRepository
    agent_repository: AgentRepository
    workflow_repository: WorkflowRepository
    agent_swarm: AgentSwarmRuntime
    judge: JudgeRuntime
    search_pool: SearchAgentPool
    workflow_service: WorkflowOrchestrator
    report_repository: ReportRepository = None
    runtime_event_repository: RuntimeEventRepository = None


def build_runtime(*, seed_demo_data: bool = False) -> AppRuntime:
    load_local_env()
    llm_provider = build_agent_llm_provider_from_env()
    evidence_store = build_evidence_store_from_env()
    (
        entity_repository,
        agent_repository,
        workflow_repository,
        report_repository,
        runtime_event_repository,
    ) = _build_runtime_repositories(seed_demo_data=seed_demo_data)
    if seed_demo_data:
        _seed_demo_evidence(evidence_store)
    agent_swarm = AgentSwarmRuntime(
        evidence_store=evidence_store,
        repository=agent_repository,
        llm_provider=llm_provider,
        runtime_event_repository=runtime_event_repository,
    )
    judge = JudgeRuntime(
        evidence_store=evidence_store,
        repository=agent_repository,
        llm_provider=llm_provider,
        runtime_event_repository=runtime_event_repository,
    )
    search_repository = _build_search_task_repository_from_env()
    search_pool = SearchAgentPool(
        providers=build_real_search_providers_from_env(),
        evidence_store=evidence_store,
        repository=search_repository,
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
        report_repository=report_repository,
        agent_swarm=agent_swarm,
        judge=judge,
        search_pool=search_pool,
        workflow_service=workflow_service,
        runtime_event_repository=runtime_event_repository,
    )


def build_evidence_store_from_env() -> EvidenceStoreClient:
    backend = os.environ.get("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "sqlite").strip().lower()
    if backend == "sqlite":
        db_path = os.environ.get("CONSENSUSINVEST_EVIDENCE_DB_PATH", "").strip()
        if not db_path:
            raise RuntimeError(
                "CONSENSUSINVEST_EVIDENCE_DB_PATH is required when "
                "CONSENSUSINVEST_EVIDENCE_STORE_BACKEND=sqlite"
            )
        return SQLiteEvidenceStoreClient(db_path)
    if backend == "memory":
        if not _env_bool("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME"):
            raise RuntimeError(
                "in-memory runtime requires CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME=1"
            )
        return InMemoryEvidenceStoreClient()
    raise RuntimeError(f"unsupported CONSENSUSINVEST_EVIDENCE_STORE_BACKEND: {backend}")


def _build_runtime_repositories(
    *,
    seed_demo_data: bool = False,
) -> tuple[
    EntityRepository,
    AgentRepository,
    WorkflowRepository,
    ReportRepository,
    RuntimeEventRepository,
]:
    if _env_bool("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME"):
        entity_repository = seed_entity_repository() if seed_demo_data else InMemoryEntityRepository()
        agent_repository = seed_demo_repository() if seed_demo_data else InMemoryAgentSwarmRepository()
        return entity_repository, agent_repository, InMemoryWorkflowRepository(), None, None

    (
        entity_db_path,
        workflow_db_path,
        agent_db_path,
        report_db_path,
        _,
        runtime_events_db_path,
    ) = _runtime_db_paths()
    entity_repository = SQLiteEntityRepository(entity_db_path)
    if seed_demo_data:
        seed = seed_entity_repository()
        for entity in seed.entities.values():
            entity_repository.upsert_entity(entity)
        for relation in seed.relations:
            entity_repository.upsert_relation(relation)
    return (
        entity_repository,
        SQLiteAgentSwarmRepository(agent_db_path),
        SQLiteWorkflowRepository(workflow_db_path),
        SQLiteReportRunRepository(report_db_path),
        SQLiteRuntimeEventRepository(runtime_events_db_path),
    )


def _build_search_task_repository_from_env() -> SQLiteSearchTaskRepository | None:
    if _env_bool("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME"):
        return None
    *_, search_db_path, _ = _runtime_db_paths()
    return SQLiteSearchTaskRepository(search_db_path)


def _seed_demo_evidence(evidence_store: EvidenceStoreClient) -> None:
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


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _runtime_db_paths() -> RuntimeDbPaths:
    raw_path = os.environ.get("CONSENSUSINVEST_RUNTIME_DB_PATH", "./data/runtime.sqlite3").strip()
    if not raw_path:
        raise RuntimeError("CONSENSUSINVEST_RUNTIME_DB_PATH must not be empty")
    if raw_path == ":memory:":
        return ":memory:", ":memory:", ":memory:", ":memory:", ":memory:", ":memory:"

    base_path = Path(raw_path).expanduser()
    base_path.parent.mkdir(parents=True, exist_ok=True)
    return (
        _module_db_path(base_path, "entities"),
        _module_db_path(base_path, "workflow"),
        _module_db_path(base_path, "agent_swarm"),
        _module_db_path(base_path, "report"),
        _module_db_path(base_path, "search_agent"),
        _module_db_path(base_path, "runtime_events"),
    )


def _module_db_path(base_path: Path, module: str) -> str:
    return str(base_path.with_name(f"{base_path.stem}.{module}{base_path.suffix}"))


__all__ = ["AppRuntime", "build_evidence_store_from_env", "build_runtime"]
