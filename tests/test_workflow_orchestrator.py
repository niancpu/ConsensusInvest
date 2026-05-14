from datetime import datetime, timezone

from consensusinvest.agent_swarm import AgentSwarmRuntime, JudgeRuntime
from consensusinvest.evidence_store import FakeEvidenceStoreClient
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget
from consensusinvest.workflow_orchestrator import InMemoryWorkflowRepository, WorkflowOrchestrator
from consensusinvest.workflow_orchestrator.models import (
    WorkflowOptions,
    WorkflowQuery,
    WorkflowRunCreate,
)


def _analysis_time() -> datetime:
    return datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)


def _seed_store(workflow_run_id: str, store: FakeEvidenceStoreClient) -> list[str]:
    envelope = InternalCallEnvelope(
        request_id="req_seed_workflow",
        correlation_id="corr_seed_workflow",
        workflow_run_id=workflow_run_id,
        analysis_time=_analysis_time(),
        requested_by="workflow_orchestrator",
        idempotency_key="seed_workflow",
    )
    result = store.ingest_search_result(
        envelope,
        SearchResultPackage(
            task_id="st_workflow_001",
            worker_id="worker_tavily",
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
                    "external_id": "workflow_news_001",
                    "title": "BYD margin improved",
                    "url": "https://example.com/workflow/001",
                    "content": "BYD reported margin improvement.",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "source_quality_hint": 0.86,
                    "metadata": {"evidence_type": "company_news"},
                },
                {
                    "external_id": "workflow_news_002",
                    "title": "BYD cash flow needs checking",
                    "url": "https://example.com/workflow/002",
                    "content": "BYD cash flow quality still needs checking.",
                    "publish_time": "2026-05-12T11:00:00+00:00",
                    "source_quality_hint": 0.74,
                    "metadata": {"evidence_type": "company_news"},
                },
            ),
            completed_at="2026-05-13T09:30:00+00:00",
        ),
    )
    return result.created_evidence_ids


def test_workflow_orchestrator_runs_swarm_judge_and_builds_trace() -> None:
    store = FakeEvidenceStoreClient()
    repository = InMemoryWorkflowRepository()
    agent_swarm = AgentSwarmRuntime(evidence_store=store)
    service = WorkflowOrchestrator(
        repository=repository,
        evidence_store=store,
        agent_swarm=agent_swarm,
        judge=JudgeRuntime(evidence_store=store, repository=agent_swarm.repository),
    )

    queued = service.create_run(
        WorkflowRunCreate(
            ticker="002594",
            stock_code="002594.SZ",
            entity_id="ent_company_002594",
            analysis_time=_analysis_time(),
            workflow_config_id="mvp_bull_judge_v1",
            query=WorkflowQuery(sources=("tavily",), evidence_types=("company_news",)),
            options=WorkflowOptions(auto_run=False),
        )
    )
    _seed_store(queued.workflow_run_id, store)
    run = service.run_once(queued.workflow_run_id)

    assert run.workflow_run_id == queued.workflow_run_id
    assert run.status == "completed"
    assert run.judgment_id is not None
    snapshot = service.snapshot(run.workflow_run_id)
    assert len(snapshot["evidence_items"]) == 2
    assert len(snapshot["agent_arguments"]) == 3
    assert len(snapshot["round_summaries"]) == 3
    assert len(snapshot["judge_tool_calls"]) == 2
    assert {call.tool_name for call in snapshot["judge_tool_calls"]} == {"get_evidence_detail"}
    assert snapshot["agent_runs"][0].rounds == (1, 2, 3)
    assert snapshot["judgment"].judgment_id == run.judgment_id
    events = service.list_events(run.workflow_run_id)
    event_types = [event.event_type for event in events]
    assert event_types.count("judge_tool_call_completed") == 2
    assert event_types.index("judge_tool_call_completed") < event_types.index("judgment_completed")
    nodes, edges = service.trace(run.workflow_run_id)
    assert any(node.node_type == "judgment" for node in nodes)
    assert any(node.node_type == "round_summary" for node in nodes)
    assert any(edge.edge_type == "uses_argument" for edge in edges)
    assert any(edge.edge_type == "uses_round_summary" for edge in edges)


def test_workflow_orchestrator_marks_insufficient_without_direct_search() -> None:
    store = FakeEvidenceStoreClient()
    agent_swarm = AgentSwarmRuntime(evidence_store=store)
    service = WorkflowOrchestrator(
        evidence_store=store,
        agent_swarm=agent_swarm,
        judge=JudgeRuntime(evidence_store=store, repository=agent_swarm.repository),
    )

    run = service.create_run(
        WorkflowRunCreate(
            ticker="002594",
            analysis_time=_analysis_time(),
            workflow_config_id="mvp_bull_judge_v1",
            options=WorkflowOptions(auto_run=True),
        )
    )

    assert run.status == "insufficient_evidence"
    assert run.failure_code == "insufficient_evidence"
    assert run.evidence_gaps
    events = service.list_events(run.workflow_run_id)
    assert [event.event_type for event in events][-1] == "workflow_failed"
