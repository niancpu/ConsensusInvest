from datetime import datetime, timezone

from consensusinvest.agent_swarm import AgentSwarmRuntime, JudgeRuntime
from consensusinvest.evidence_store import FakeEvidenceStoreClient
from consensusinvest.runtime import InternalCallEnvelope, SQLiteRuntimeEventRepository
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget


def _envelope(*, idempotency_key: str = "agent_runtime_events") -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="req_agent_runtime_events_001",
        correlation_id="corr_agent_runtime_events_001",
        workflow_run_id="wr_agent_runtime_events_001",
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="workflow_orchestrator",
        idempotency_key=idempotency_key,
        trace_level="standard",
    )


def _store_with_evidence() -> FakeEvidenceStoreClient:
    store = FakeEvidenceStoreClient()
    store.ingest_search_result(
        _envelope(idempotency_key="seed_agent_runtime_events"),
        SearchResultPackage(
            task_id="st_agent_runtime_events_001",
            worker_id="worker_tavily",
            source="tavily",
            source_type="web_news",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("比亚迪",),
            ),
            items=(
                {
                    "external_id": "news_001",
                    "title": "比亚迪盈利改善",
                    "url": "https://example.com/news/001",
                    "content": "比亚迪公开披露盈利改善。",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "source_quality_hint": 0.86,
                },
                {
                    "external_id": "news_002",
                    "title": "现金流质量待核对",
                    "url": "https://example.com/news/002",
                    "content": "现金流质量仍需核对。",
                    "publish_time": "2026-05-12T11:00:00+00:00",
                    "source_quality_hint": 0.74,
                },
            ),
            completed_at="2026-05-13T09:00:00+00:00",
            metadata={"evidence_type": "company_news"},
        ),
    )
    return store


def test_agent_swarm_writes_runtime_events_without_changing_output(tmp_path):
    event_repository = SQLiteRuntimeEventRepository(tmp_path / "runtime_events.sqlite3")
    runtime = AgentSwarmRuntime(
        evidence_store=_store_with_evidence(),
        runtime_event_repository=event_repository,
    )

    outcome = runtime.run(
        _envelope(idempotency_key="run_swarm_runtime_events"),
        {
            "workflow_run_id": "wr_agent_runtime_events_001",
            "ticker": "002594",
            "entity_id": "ent_company_002594",
            "workflow_config_id": "mvp_bull_judge_v1",
            "evidence_selection": {"evidence_ids": ["ev_000001", "ev_000002"]},
        },
    )

    assert outcome.status == "completed"
    assert len(outcome.agent_argument_ids) == 3
    assert len(outcome.round_summary_ids) == 3
    events = event_repository.list_events(
        workflow_run_id="wr_agent_runtime_events_001",
        correlation_id="corr_agent_runtime_events_001",
    )
    assert [event.event_type for event in events].count("started") == 2
    assert [event.event_type for event in events].count("completed") == 2
    assert any(
        event.event_type == "status_changed"
        and event.payload["agent_argument_id"] == outcome.agent_argument_ids[0]
        and "argument" not in event.payload
        for event in events
    )
    swarm_completed = events[-1]
    assert swarm_completed.producer == "agent_swarm"
    assert swarm_completed.payload["status"] == "completed"
    assert swarm_completed.payload["agent_argument_ids"] == list(outcome.agent_argument_ids)
    event_repository.close()


def test_judge_writes_runtime_events_without_changing_output(tmp_path):
    event_repository = SQLiteRuntimeEventRepository(tmp_path / "runtime_events.sqlite3")
    store = _store_with_evidence()
    swarm = AgentSwarmRuntime(
        evidence_store=store,
        runtime_event_repository=event_repository,
    )
    swarm_outcome = swarm.run(
        _envelope(idempotency_key="run_swarm_before_judge_runtime_events"),
        {
            "workflow_run_id": "wr_agent_runtime_events_001",
            "ticker": "002594",
            "entity_id": "ent_company_002594",
            "workflow_config_id": "mvp_bull_judge_v1",
            "evidence_selection": {"evidence_ids": ["ev_000001", "ev_000002"]},
        },
    )
    judge = JudgeRuntime(
        evidence_store=store,
        repository=swarm.repository,
        runtime_event_repository=event_repository,
    )

    outcome = judge.run(
        _envelope(idempotency_key="run_judge_runtime_events"),
        {
            "workflow_run_id": "wr_agent_runtime_events_001",
            "round_summary_ids": list(swarm_outcome.round_summary_ids),
            "agent_argument_ids": list(swarm_outcome.agent_argument_ids),
            "key_evidence_ids": ["ev_000001", "ev_000002"],
        },
    )

    assert outcome.status == "completed"
    assert outcome.judgment_id is not None
    judgment = swarm.repository.get_judgment(outcome.judgment_id)
    assert judgment is not None
    assert judgment.final_signal == "neutral"
    judge_events = event_repository.list_events(
        workflow_run_id="wr_agent_runtime_events_001",
        producer="judge_runtime",
    )
    assert [event.event_type for event in judge_events] == [
        "started",
        "tool_call_finished",
        "tool_call_finished",
        "completed",
    ]
    assert judge_events[0].correlation_id == "corr_agent_runtime_events_001"
    assert judge_events[1].payload["tool_name"] == "get_evidence_detail"
    assert judge_events[1].payload["input"] == {"evidence_id": "ev_000001"}
    assert "judgment" not in judge_events[-1].payload
    assert "reasoning" not in judge_events[-1].payload
    assert judge_events[-1].payload["judgment_id"] == outcome.judgment_id
    event_repository.close()


def test_insufficient_evidence_paths_write_failed_runtime_events(tmp_path):
    event_repository = SQLiteRuntimeEventRepository(tmp_path / "runtime_events.sqlite3")
    swarm = AgentSwarmRuntime(
        evidence_store=FakeEvidenceStoreClient(),
        runtime_event_repository=event_repository,
    )
    swarm_outcome = swarm.run(
        _envelope(idempotency_key="run_swarm_gap_runtime_events"),
        {
            "workflow_run_id": "wr_agent_runtime_events_001",
            "ticker": "002594",
            "entity_id": "ent_company_002594",
            "workflow_config_id": "mvp_bull_judge_v1",
            "evidence_selection": {"evidence_ids": []},
        },
    )
    judge = JudgeRuntime(
        evidence_store=FakeEvidenceStoreClient(),
        repository=swarm.repository,
        runtime_event_repository=event_repository,
    )
    judge_outcome = judge.run(
        _envelope(idempotency_key="run_judge_gap_runtime_events"),
        {
            "workflow_run_id": "wr_agent_runtime_events_001",
            "round_summary_ids": [],
            "agent_argument_ids": [],
            "key_evidence_ids": [],
        },
    )

    assert swarm_outcome.status == "insufficient_evidence"
    assert judge_outcome.status == "insufficient_evidence"
    failed_events = [
        event
        for event in event_repository.list_events(
            workflow_run_id="wr_agent_runtime_events_001",
            correlation_id="corr_agent_runtime_events_001",
        )
        if event.event_type == "failed"
    ]
    assert [event.producer for event in failed_events] == ["agent_swarm", "judge_runtime"]
    assert failed_events[0].payload["gap_types"] == ["missing_core_evidence"]
    assert failed_events[1].payload["gap_types"] == ["missing_judge_inputs"]
    assert all("description" not in event.payload for event in failed_events)
    event_repository.close()
