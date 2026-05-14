from datetime import datetime, timezone

import pytest

from consensusinvest.agent_swarm.models import EvidenceGap, SuggestedSearch
from consensusinvest.workflow_orchestrator import SQLiteWorkflowRepository
from consensusinvest.workflow_orchestrator.models import (
    WorkflowOptions,
    WorkflowProgress,
    WorkflowQuery,
    WorkflowRunRecord,
)


def _time(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 13, hour, minute, tzinfo=timezone.utc)


def _run(workflow_run_id: str, *, ticker: str = "002594", created_at: datetime | None = None) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        workflow_run_id=workflow_run_id,
        correlation_id=f"corr_{workflow_run_id}",
        ticker=ticker,
        analysis_time=_time(10),
        workflow_config_id="mvp_bull_judge_v1",
        status="queued",
        stage="queued",
        query=WorkflowQuery(
            lookback_days=15,
            sources=("tavily",),
            evidence_types=("company_news",),
            max_results=12,
        ),
        options=WorkflowOptions(stream=True, include_raw_payload=True, auto_run=False),
        entity_id=f"ent_company_{ticker}",
        stock_code=f"{ticker}.SZ",
        created_at=created_at or _time(10),
    )


def test_sqlite_workflow_repository_creates_updates_and_restores_run(tmp_path) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflow.sqlite3")
    run = repository.create_run(_run("wr_20260513_002594_000001"))

    progress = WorkflowProgress(
        raw_items_collected=2,
        evidence_items_normalized=2,
        evidence_items_structured=1,
        agent_arguments_completed=3,
    )
    gap = EvidenceGap(
        gap_type="missing_cash_flow",
        description="cash flow evidence is missing",
        suggested_search=SuggestedSearch(
            target_entity_ids=("ent_company_002594",),
            evidence_types=("financial_report",),
            lookback_days=90,
            keywords=("cash flow", "BYD"),
        ),
    )
    updated = repository.update_run(
        run.workflow_run_id,
        status="failed",
        stage="failed",
        completed_at=_time(10, 30),
        progress=progress,
        failure_code="insufficient_evidence",
        failure_message="Evidence is insufficient.",
        evidence_gaps=(gap,),
        search_task_ids=("st_001",),
    )

    assert run.status == "queued"
    assert updated is not run
    assert updated.status == "failed"
    assert updated.progress == progress
    assert updated.evidence_gaps == (gap,)
    assert updated.search_task_ids == ("st_001",)
    assert repository.get_run(run.workflow_run_id) == updated

    repository.close()
    reopened = SQLiteWorkflowRepository(tmp_path / "workflow.sqlite3")
    assert reopened.get_run(run.workflow_run_id) == updated


def test_sqlite_workflow_repository_lists_runs_with_filters_and_pagination(tmp_path) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflow.sqlite3")
    older = repository.create_run(_run("wr_20260513_002594_000001", created_at=_time(9)))
    newer = repository.create_run(_run("wr_20260513_002594_000002", created_at=_time(11)))
    other = repository.create_run(_run("wr_20260513_000001_000003", ticker="000001", created_at=_time(12)))
    repository.update_run(other.workflow_run_id, status="completed", stage="completed", completed_at=_time(12, 30))

    rows, total = repository.list_runs(ticker="002594", limit=10, offset=0)
    assert total == 2
    assert [row.workflow_run_id for row in rows] == [newer.workflow_run_id, older.workflow_run_id]

    rows, total = repository.list_runs(status="completed", limit=1, offset=0)
    assert total == 1
    assert [row.workflow_run_id for row in rows] == [other.workflow_run_id]

    rows, total = repository.list_runs(limit=1, offset=1)
    assert total == 3
    assert [row.workflow_run_id for row in rows] == [newer.workflow_run_id]


def test_sqlite_workflow_repository_appends_events_and_filters_after_sequence(tmp_path) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflow.sqlite3")
    run = repository.create_run(_run("wr_20260513_002594_000001"))
    other = repository.create_run(_run("wr_20260513_000001_000002", ticker="000001"))

    first = repository.append_event(run.workflow_run_id, "workflow_queued", {"ticker": run.ticker}, created_at=_time(10))
    second = repository.append_event(run.workflow_run_id, "workflow_started", created_at=_time(10, 1))
    other_first = repository.append_event(other.workflow_run_id, "workflow_queued", created_at=_time(10, 2))

    assert first.sequence == 1
    assert first.event_id.endswith("_000001")
    assert second.sequence == 2
    assert other_first.sequence == 1
    assert repository.last_event_sequence(run.workflow_run_id) == 2
    assert repository.list_events(run.workflow_run_id, after_sequence=1) == [second]

    repository.close()
    reopened = SQLiteWorkflowRepository(tmp_path / "workflow.sqlite3")
    third = reopened.append_event(run.workflow_run_id, "workflow_completed", created_at=_time(10, 3))
    assert third.sequence == 3
    assert [event.sequence for event in reopened.list_events(run.workflow_run_id)] == [1, 2, 3]
    assert reopened.list_events(run.workflow_run_id)[0].payload == {"ticker": "002594"}


def test_sqlite_workflow_repository_new_workflow_run_id_persists_sequence(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    repository = SQLiteWorkflowRepository(db_path)

    first = repository.new_workflow_run_id(ticker="002594", analysis_time=_time(10))
    second = repository.new_workflow_run_id(ticker="002594", analysis_time=_time(10))
    repository.close()

    reopened = SQLiteWorkflowRepository(db_path)
    third = reopened.new_workflow_run_id(ticker="002594", analysis_time=_time(10))

    assert first == "wr_20260513_002594_000001"
    assert second == "wr_20260513_002594_000002"
    assert third == "wr_20260513_002594_000003"


def test_sqlite_workflow_repository_update_missing_matches_in_memory_error(tmp_path) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflow.sqlite3")

    with pytest.raises(KeyError):
        repository.update_run("missing", status="failed")
