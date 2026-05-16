"""Report Module smoke tests for runtime-backed, non-fixture behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from consensusinvest.agent_swarm.models import JudgmentRecord
from consensusinvest.agent_swarm.repository import InMemoryAgentSwarmRepository
from consensusinvest.app import create_app
from consensusinvest.entities.repository import EntityRecord, InMemoryEntityRepository
from consensusinvest.entities.repository import EntityRelationRecord
from consensusinvest.evidence_store.client import InMemoryEvidenceStoreClient
from consensusinvest.evidence_store.models import EvidenceReferenceQuery, EvidenceStructureDraft, MarketSnapshotDraft
from consensusinvest.report_module.repository import SQLiteReportRunRepository
from consensusinvest.report_module.service import (
    ReportRuntimeReader,
    build_benefits_risks_view,
    build_concept_radar,
    build_event_impact_ranking,
    build_industry_details_view,
    build_index_intraday,
    build_index_overview,
    build_market_stocks,
    build_market_warnings,
    build_stock_analysis_view,
)
from consensusinvest.report_module.schemas import RefreshPolicy
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchTaskStatus
from consensusinvest.workflow_orchestrator.models import (
    WorkflowOptions,
    WorkflowProgress,
    WorkflowQuery,
    WorkflowRunRecord,
)
from consensusinvest.workflow_orchestrator.repository import InMemoryWorkflowRepository


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_search_returns_empty_missing_state_without_seeded_fixture_data(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/search", params={"keyword": "比亚迪"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["data_state"] == "missing"


def test_search_keyword_required(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/search")
    assert r.status_code in {400, 422}
    body = r.json()
    assert "error" in body or "detail" in body


def test_analysis_unknown_stock_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/002594.SZ/analysis")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "STOCK_NOT_FOUND"


def test_market_index_overview_empty_store_requests_refresh(client: TestClient) -> None:
    r = client.get("/api/v1/market/index-overview")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["indices"] == []
    assert data["data_state"] == "pending_refresh"
    assert data["refresh_task_id"]


def test_market_index_intraday_empty_store_requests_refresh(client: TestClient) -> None:
    client.app.state.runtime.search_pool.providers = {}
    r = client.get("/api/v1/market/index-intraday", params={"code": "000001.SH"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["code"] == "000001.SH"
    assert data["points"] == []
    assert data["data_state"] == "pending_refresh"
    assert data["refresh_task_id"]


def test_market_index_overview_api_writes_report_run(client: TestClient, tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    client.app.state.report_repository = repo
    try:
        r = client.get("/api/v1/market/index-overview")
    finally:
        delattr(client.app.state, "report_repository")

    assert r.status_code == 200, r.text
    refresh_task_id = r.json()["data"]["refresh_task_id"]
    run = repo.list_runs(limit=1, status="pending_refresh")[0]
    assert run.refresh_task_id == refresh_task_id
    assert run.output_snapshot["refresh_task_id"] == refresh_task_id
    repo.close()


def test_market_index_intraday_projects_snapshot_points(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_market_snapshot_draft(
        repo,
        MarketSnapshotDraft(
            snapshot_type="index_quote",
            ticker="000001",
            source="akshare",
            snapshot_time="2026-05-13T09:31:00+00:00",
            metrics={
                "code": "000001.SH",
                "name": "上证指数",
                "value": 3121.5,
                "open": 3120.1,
                "high": 3122.0,
                "low": 3119.8,
                "previous_close": 3118.2,
                "intraday_points": [
                    {"time": "09:30", "timestamp": "2026-05-13T09:30:00+08:00", "value": 3120.1},
                    {"time": "09:31", "timestamp": "2026-05-13T09:31:00+08:00", "value": 3121.5},
                ],
            },
        ),
    )

    view, refresh_task_id = build_index_intraday(reader=reader, code="000001.SH", refresh=RefreshPolicy.STALE)

    assert refresh_task_id is None
    assert view.data_state == "ready"
    assert view.name == "上证指数"
    assert [point.value for point in view.points] == [3120.1, 3121.5]
    assert view.open == 3120.1
    assert view.snapshot_ids
    repo.close()


def test_market_index_intraday_refresh_runs_search_agent_and_reprojects_snapshot(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _empty_reader(repo)
    reader.search_pool = FakeImmediateMarketSearchPool(reader.evidence_store)

    view, refresh_task_id = build_index_intraday(reader=reader, code="000001.SH", refresh=RefreshPolicy.STALE)

    assert refresh_task_id == "st_intraday_refresh_001"
    assert reader.search_pool.ran_task_ids == ["st_intraday_refresh_001"]
    assert view.data_state == "ready"
    assert view.points[0].time == "09:30"
    assert [point.value for point in view.points] == [3120.1, 3121.5]
    assert view.snapshot_ids
    _, search_task = reader.search_pool.calls[0]
    assert search_task.scope.sources == ("akshare",)
    repo.close()


def test_market_index_intraday_refresh_key_includes_index_code(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _empty_reader(repo)
    reader.search_pool = FakeSearchPool(task_ids=("st_sh_001", "st_sz_001"))

    build_index_intraday(reader=reader, code="000001.SH", refresh=RefreshPolicy.STALE)
    build_index_intraday(reader=reader, code="399001.SZ", refresh=RefreshPolicy.STALE)

    keys = [envelope.idempotency_key for envelope, _ in reader.search_pool.calls]
    assert keys[0] != keys[1]
    assert keys[0].endswith("_index_intraday_missing_000001_SH")
    assert keys[1].endswith("_index_intraday_missing_399001_SZ")
    repo.close()


def test_market_index_intraday_existing_failed_refresh_reports_failed(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _empty_reader(repo)
    reader.search_pool = FakeFailedMarketSearchPool()

    view, refresh_task_id = build_index_intraday(reader=reader, code="000001.SH", refresh=RefreshPolicy.STALE)

    assert refresh_task_id == "st_failed_intraday"
    assert view.data_state == "failed"
    assert view.points == []
    repo.close()


def test_market_index_intraday_refresh_exception_reports_failed(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _empty_reader(repo)
    reader.search_pool = FakeRaisingMarketSearchPool()

    view, refresh_task_id = build_index_intraday(reader=reader, code="000001.SH", refresh=RefreshPolicy.STALE)

    assert refresh_task_id == "st_raising_intraday"
    assert view.data_state == "failed"
    assert view.points == []
    repo.close()


def test_market_stocks_empty_store_requests_refresh(client: TestClient) -> None:
    r = client.get("/api/v1/market/stocks", params={"page": 1, "page_size": 1})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["list"] == []
    assert data["pagination"] == {"page": 1, "page_size": 1, "total": 0}
    assert data["data_state"] == "pending_refresh"


def test_concept_radar_empty_store_returns_missing(client: TestClient) -> None:
    r = client.get("/api/v1/market/concept-radar", params={"limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["data_state"] == "missing"


def test_warnings_severity_validation(client: TestClient) -> None:
    r = client.get("/api/v1/market/warnings", params={"severity": "bogus"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_warnings_empty_store_returns_missing(client: TestClient) -> None:
    r = client.get("/api/v1/market/warnings", params={"severity": "notice"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["data_state"] == "missing"


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_stock_report_views_create_report_run_records(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_stock(repo)

    analysis, refresh_task_id = build_stock_analysis_view(
        reader=reader,
        stock_code="002594.SZ",
        query=None,
        workflow_run_id=None,
        latest=True,
        refresh=RefreshPolicy.NEVER,
    )
    benefits_risks = build_benefits_risks_view(
        reader=reader,
        stock_code="002594.SZ",
        workflow_run_id=None,
    )

    analysis_run = repo.get_run(analysis.report_run_id)
    benefits_run = repo.get_run(benefits_risks.report_run_id)
    analysis_cache = repo.get_view_cache(analysis.report_run_id)
    benefits_cache = repo.get_view_cache(benefits_risks.report_run_id)

    assert analysis_run is not None
    assert analysis_cache is not None
    assert refresh_task_id is None
    assert analysis_run.status == "completed"
    assert analysis_run.report_mode == "report_generation"
    assert analysis_run.stock_code == "002594.SZ"
    assert analysis_run.workflow_run_id is None
    assert analysis_run.judgment_id is None
    assert analysis_run.input_refs["evidence_ids"] == ["ev_000001"]
    assert analysis_run.output_snapshot["report_run_id"] == analysis.report_run_id
    assert analysis_run.output_snapshot["report"]["key_evidence"][0]["evidence_id"] == "ev_000001"
    assert analysis_run.output_snapshot["report"]["key_evidence"][0]["publish_time"] == "2026-05-13T00:00:00+00:00"
    assert analysis_run.output_snapshot["report"]["key_evidence"][0]["fetched_at"]
    assert analysis_cache.cache_key == analysis.report_run_id
    assert analysis_cache.report_run_id == analysis_run.report_run_id
    assert analysis_cache.input_refs == analysis_run.input_refs
    assert analysis_cache.output_snapshot == analysis_run.output_snapshot

    assert benefits_run is not None
    assert benefits_cache is not None
    assert benefits_run.output_snapshot["report_run_id"] == benefits_risks.report_run_id
    assert benefits_run.input_refs["evidence_ids"] == ["ev_000001"]
    assert benefits_cache.report_run_id == benefits_run.report_run_id
    repo.close()


def test_report_run_saves_report_view_cited_references_and_tolerates_missing_evidence(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_stock(repo)

    analysis, _ = build_stock_analysis_view(
        reader=reader,
        stock_code="002594.SZ",
        query=None,
        workflow_run_id=None,
        latest=True,
        refresh=RefreshPolicy.NEVER,
    )
    refs = reader.evidence_store.query_references(
        _envelope(),
        EvidenceReferenceQuery(
            source_type="report_view",
            source_id=analysis.report_run_id,
            reference_role="cited",
        ),
    )
    assert [(ref.source_id, ref.evidence_id, ref.reference_role) for ref in refs] == [
        (analysis.report_run_id, "ev_000001", "cited")
    ]

    missing_reader = _reader_with_missing_judgment_evidence(repo)
    missing_view = build_benefits_risks_view(
        reader=missing_reader,
        stock_code="002594.SZ",
        workflow_run_id="wr_missing_refs",
    )
    missing_refs = missing_reader.evidence_store.query_references(
        _envelope(),
        EvidenceReferenceQuery(source_type="report_view", source_id=missing_view.report_run_id),
    )
    assert missing_refs == []
    repo.close()


def test_stock_analysis_ignores_incomplete_workflow_rows_when_selecting_latest_judgment(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_stock_entity_only(repo)

    class IncompleteRun:
        def __init__(self, workflow_run_id: str) -> None:
            self.workflow_run_id = workflow_run_id
            self.entity_id = "ent_company_002594"

    class FakeWorkflowRepository:
        def list_runs(self, *, ticker: str | None = None, status: str | None = None, limit: int = 20, offset: int = 0):
            _ = status
            assert ticker == "002594"
            if offset == 0:
                return [IncompleteRun("wr_incomplete"), WorkflowRunRecord(
                    workflow_run_id="wr_complete",
                    correlation_id="corr_complete",
                    ticker="002594",
                    analysis_time=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
                    workflow_config_id="cfg_default",
                    status="completed",
                    stage="judge",
                    query=WorkflowQuery(),
                    options=WorkflowOptions(),
                    entity_id="ent_company_002594",
                    stock_code="002594.SZ",
                    created_at=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
                    started_at=None,
                    completed_at=datetime(2026, 5, 13, 9, 5, tzinfo=timezone.utc),
                    judgment_id="jdg_complete",
                    final_signal="positive",
                    confidence=0.7,
                    progress=WorkflowProgress(),
                    failure_code=None,
                    failure_message=None,
                    evidence_gaps=(),
                    search_task_ids=(),
                )], 2
            return [], 2

    reader.workflow_repository = FakeWorkflowRepository()
    reader.agent_repository.save_judgment(
        JudgmentRecord(
            judgment_id="jdg_complete",
            workflow_run_id="wr_complete",
            final_signal="positive",
            confidence=0.7,
            time_horizon="short_term",
            key_positive_evidence_ids=(),
            key_negative_evidence_ids=(),
            reasoning="完整 workflow 行仍可提供最新 judgment。",
            risk_notes=(),
            referenced_agent_argument_ids=(),
            limitations=(),
            created_at=datetime(2026, 5, 13, 9, 5, tzinfo=timezone.utc),
        )
    )

    view, refresh_task_id = build_stock_analysis_view(
        reader=reader,
        stock_code="002594.SZ",
        query=None,
        workflow_run_id=None,
        latest=True,
        refresh=RefreshPolicy.NEVER,
    )

    assert refresh_task_id is None
    assert view.data_state == "ready"
    assert view.workflow_run_id == "wr_complete"
    assert view.judgment_id == "jdg_complete"
    assert view.action is not None
    repo.close()


    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_industry_relation(repo)

    view = build_industry_details_view(
        reader=reader,
        stock_code="002594.SZ",
        workflow_run_id=None,
    )

    assert view.stock_code == "002594.SZ"
    assert view.ticker == "002594"
    assert view.industry_entity_id == "ent_industry_nev"
    assert view.industry_name == "新能源汽车"
    assert view.policy_support_level == "high"
    assert view.policy_support_desc == "政策支持力度较强"
    assert view.supply_demand_status == "供需紧平衡"
    assert view.competition_landscape == "头部集中度提升"
    assert view.referenced_evidence_ids == ["ev_000001"]
    assert view.links.entity == "/api/v1/entities/ent_industry_nev"
    repo.close()


def test_event_impact_ranking_reads_objective_event_evidence(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_event_evidence(repo)

    view = build_event_impact_ranking(
        reader=reader,
        stock_code="002594.SZ",
        workflow_run_id=None,
        limit=5,
    )

    assert view.stock_code == "002594.SZ"
    assert view.ranker == "report_event_impact_ranker_v1"
    assert [item.event_name for item in view.items] == ["董事会公告产能规划"]
    assert view.items[0].direction is None
    assert view.items[0].evidence_ids == ["ev_000001"]
    assert view.items[0].impact_level == "high"
    repo.close()


def test_market_report_runs_store_snapshot_refs_and_refresh_task(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _empty_reader(repo)
    reader.search_pool = FakeSearchPool(task_ids=("st_real_market_index_001", "st_real_market_stocks_001"))

    overview, refresh_task_id = build_index_overview(reader=reader, refresh=RefreshPolicy.STALE)
    stocks = build_market_stocks(
        reader=reader,
        page=1,
        page_size=20,
        keyword=None,
        refresh=RefreshPolicy.STALE,
    )

    assert refresh_task_id == "st_real_market_index_001"
    assert stocks.refresh_task_id == "st_real_market_stocks_001"
    assert len(reader.search_pool.calls) == 2
    index_envelope, index_task = reader.search_pool.calls[0]
    stocks_envelope, stocks_task = reader.search_pool.calls[1]
    assert index_envelope.requested_by == "report_module"
    assert index_envelope.workflow_run_id is None
    assert index_envelope.idempotency_key is not None
    assert stocks_envelope.requested_by == "report_module"
    assert stocks_envelope.workflow_run_id is None
    assert stocks_envelope.idempotency_key is not None
    assert index_task.task_type == "market_snapshot"
    assert stocks_task.task_type == "market_snapshot"
    assert index_task.target.metadata["market_view"] == "index_overview"
    assert stocks_task.target.metadata["market_view"] == "market_stocks"
    assert index_task.callback is not None
    assert index_task.callback.ingest_target == "evidence_store"
    assert stocks_task.callback is not None
    assert stocks_task.callback.ingest_target == "evidence_store"
    pending_runs = repo.list_runs(limit=10, status="pending_refresh")
    overview_run = next(run for run in pending_runs if "indices" in run.output_snapshot)
    overview_cache = repo.get_view_cache(overview_run.report_run_id)
    assert overview_cache is not None
    assert overview_run.output_snapshot["refresh_task_id"] == refresh_task_id
    assert overview_run.refresh_task_id == refresh_task_id
    assert overview_run.input_refs["market_snapshot_ids"] == []
    assert overview_cache.report_run_id == overview_run.report_run_id
    assert overview_cache.data_state == overview_run.data_state
    assert overview_cache.output_snapshot == overview_run.output_snapshot

    stock_run = next(run for run in pending_runs if "list" in run.output_snapshot)
    stock_cache = repo.get_view_cache(stock_run.report_run_id)
    assert stock_cache is not None
    assert stock_run.output_snapshot["refresh_task_id"] == stocks.refresh_task_id
    assert stock_run.refresh_task_id == stocks.refresh_task_id
    assert stock_cache.report_run_id == stock_run.report_run_id
    repo.close()


def test_market_stocks_report_run_stores_snapshot_refs(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_market_snapshot(repo)

    payload = build_market_stocks(
        reader=reader,
        page=1,
        page_size=20,
        keyword=None,
        refresh=RefreshPolicy.STALE,
    )
    run = repo.get_run(repo.list_runs(limit=1)[0].report_run_id)

    assert payload.refresh_task_id is None
    assert run is not None
    assert run.status == "completed"
    assert run.input_refs["market_snapshot_ids"] == [payload.list[0].snapshot_id]
    assert run.output_snapshot["list"][0]["snapshot_id"] == payload.list[0].snapshot_id
    repo.close()


def test_concept_radar_report_run_stores_snapshot_and_evidence_refs(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_concept_snapshot(repo)

    items, data_state = build_concept_radar(reader=reader, limit=20)
    run = repo.get_run(repo.list_runs(limit=1)[0].report_run_id)

    assert data_state.value == "ready"
    assert run is not None
    assert run.status == "completed"
    assert run.ticker == "MARKET_CONCEPT_RADAR"
    assert run.input_refs["market_snapshot_ids"] == items[0].snapshot_ids
    assert run.input_refs["evidence_ids"] == ["ev_concept_001"]
    assert run.output_snapshot["data_state"] == "ready"
    assert run.output_snapshot["items"][0]["snapshot_ids"] == items[0].snapshot_ids
    assert run.output_snapshot["items"][0]["evidence_ids"] == items[0].evidence_ids
    assert run.limitations
    repo.close()


def test_market_warnings_report_run_stores_snapshot_and_evidence_refs(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_warning_snapshot(repo)

    items, data_state = build_market_warnings(reader=reader, limit=20, severity="notice")
    run = repo.get_run(repo.list_runs(limit=1)[0].report_run_id)

    assert data_state.value == "ready"
    assert run is not None
    assert run.status == "completed"
    assert run.ticker == "MARKET_WARNINGS"
    assert run.input_refs["market_snapshot_ids"] == items[0].snapshot_ids
    assert run.input_refs["evidence_ids"] == ["ev_warning_001"]
    assert run.output_snapshot["data_state"] == "ready"
    assert run.output_snapshot["items"][0]["snapshot_ids"] == items[0].snapshot_ids
    assert run.output_snapshot["items"][0]["evidence_ids"] == items[0].evidence_ids
    assert run.refresh_task_id is None
    repo.close()


def test_market_list_views_write_report_run_when_missing(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _empty_reader(repo)

    concept_items, concept_state = build_concept_radar(reader=reader, limit=20)
    warning_items, warning_state = build_market_warnings(reader=reader, limit=20, severity=None)
    runs = repo.list_runs(limit=10)

    assert concept_items == []
    assert warning_items == []
    assert concept_state.value == "missing"
    assert warning_state.value == "missing"
    assert {run.ticker for run in runs} == {"MARKET_CONCEPT_RADAR", "MARKET_WARNINGS"}
    for run in runs:
        assert run.input_refs["market_snapshot_ids"] == []
        assert run.input_refs["evidence_ids"] == []
        assert run.output_snapshot == {"items": [], "data_state": "missing"}
        assert run.refresh_task_id is None
    repo.close()


def test_latest_judgment_for_entity_uses_latest_workflow_run(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_stock(repo)
    workflow_repository = InMemoryWorkflowRepository()
    reader.workflow_repository = workflow_repository

    older_run = _workflow_run(
        workflow_run_id="wr_20260512_002594_000001",
        created_at=datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        entity_id="ent_company_002594",
        stock_code="002594.SZ",
        ticker="002594",
    )
    latest_run = _workflow_run(
        workflow_run_id="wr_20260513_002594_000001",
        created_at=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
        entity_id="ent_company_002594",
        stock_code="002594.SZ",
        ticker="002594",
    )
    workflow_repository.create_run(older_run)
    workflow_repository.create_run(latest_run)
    reader.agent_repository.save_judgment(
        JudgmentRecord(
            judgment_id="jdg_older",
            workflow_run_id=older_run.workflow_run_id,
            final_signal="neutral",
            confidence=0.5,
            time_horizon="short_term",
            reasoning="older judgment",
            created_at=older_run.created_at,
        )
    )
    reader.agent_repository.save_judgment(
        JudgmentRecord(
            judgment_id="jdg_latest",
            workflow_run_id=latest_run.workflow_run_id,
            final_signal="positive",
            confidence=0.8,
            time_horizon="short_term",
            reasoning="latest judgment",
            created_at=latest_run.created_at,
        )
    )

    view, refresh_task_id = build_stock_analysis_view(
        reader=reader,
        stock_code="002594.SZ",
        query=None,
        workflow_run_id=None,
        latest=True,
        refresh=RefreshPolicy.NEVER,
    )

    assert refresh_task_id is None
    assert view.workflow_run_id == latest_run.workflow_run_id
    assert view.judgment_id == "jdg_latest"
    assert view.report_mode == "with_workflow_trace"
    assert view.action is not None
    assert view.action.signal == "positive"
    repo.close()


def test_stock_analysis_refresh_submits_real_search_task_and_persists_task_id(tmp_path: Path) -> None:
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")
    reader = _reader_with_stock_entity_only(repo)
    reader.search_pool = FakeSearchPool(task_id="st_real_refresh_001")

    view, refresh_task_id = build_stock_analysis_view(
        reader=reader,
        stock_code="002594.SZ",
        query="比亚迪 基本面",
        workflow_run_id=None,
        latest=True,
        refresh=RefreshPolicy.MISSING,
    )

    assert refresh_task_id == "st_real_refresh_001"
    assert view.data_state == "refreshing"
    assert view.workflow_run_id is None
    assert view.judgment_id is None

    submit_envelope, search_task = reader.search_pool.calls[0]
    assert submit_envelope.requested_by == "report_module"
    assert submit_envelope.workflow_run_id is None
    assert submit_envelope.idempotency_key is not None
    assert search_task.task_type == "stock_research"
    assert search_task.callback is not None
    assert search_task.callback.ingest_target == "evidence_store"
    assert search_task.callback.workflow_run_id is None
    assert search_task.target.ticker == "002594"
    assert search_task.target.stock_code == "002594.SZ"
    assert search_task.target.entity_id == "ent_company_002594"
    assert "比亚迪 基本面" in search_task.target.keywords

    run = repo.get_run(view.report_run_id)
    assert run is not None
    assert run.status == "refreshing"
    assert run.refresh_task_id == refresh_task_id
    assert run.output_snapshot["refresh_task_id"] == refresh_task_id
    repo.close()


def _empty_reader(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    return ReportRuntimeReader(
        evidence_store=InMemoryEvidenceStoreClient(),
        entity_repository=InMemoryEntityRepository(),
        agent_repository=InMemoryAgentSwarmRepository(),
        workflow_repository=InMemoryWorkflowRepository(),
        report_repository=repo,
    )


def _reader_with_stock(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    evidence_store = InMemoryEvidenceStoreClient()
    entity_repository = InMemoryEntityRepository(
        entities={
            "ent_company_002594": EntityRecord(
                entity_id="ent_company_002594",
                entity_type="company",
                name="比亚迪",
                aliases=("002594", "002594.SZ"),
            )
        }
    )
    envelope = _envelope()
    result = evidence_store.ingest_search_result(
        envelope,
        {
            "task_id": "st_test",
            "source": "test",
            "source_type": "report",
            "target": {"ticker": "002594", "entity_id": "ent_company_002594"},
            "items": [
                {
                    "external_id": "risk_001",
                    "title": "风险披露",
                    "content": "现金流质量需要继续核对。",
                    "ticker": "002594",
                    "entity_ids": ["ent_company_002594"],
                    "evidence_type": "risk_disclosure",
                    "publish_time": "2026-05-13T00:00:00+00:00",
                }
            ],
        },
    )
    evidence_store.save_structure(
        envelope,
        EvidenceStructureDraft(
            evidence_id=result.created_evidence_ids[0],
            objective_summary="现金流质量需要继续核对。",
        ),
    )
    return ReportRuntimeReader(
        evidence_store=evidence_store,
        entity_repository=entity_repository,
        agent_repository=InMemoryAgentSwarmRepository(),
        workflow_repository=InMemoryWorkflowRepository(),
        report_repository=repo,
    )


def _reader_with_stock_entity_only(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    return ReportRuntimeReader(
        evidence_store=InMemoryEvidenceStoreClient(),
        entity_repository=InMemoryEntityRepository(
            entities={
                "ent_company_002594": EntityRecord(
                    entity_id="ent_company_002594",
                    entity_type="company",
                    name="比亚迪",
                    aliases=("002594", "002594.SZ", "BYD"),
                )
            }
        ),
        agent_repository=InMemoryAgentSwarmRepository(),
        workflow_repository=InMemoryWorkflowRepository(),
        report_repository=repo,
    )


def _reader_with_missing_judgment_evidence(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    reader = _reader_with_stock_entity_only(repo)
    reader.agent_repository.save_judgment(
        JudgmentRecord(
            judgment_id="jdg_missing_refs",
            workflow_run_id="wr_missing_refs",
            final_signal="neutral",
            confidence=0.5,
            time_horizon="short_term",
            key_positive_evidence_ids=("ev_missing_positive",),
            key_negative_evidence_ids=("ev_missing_negative",),
            reasoning="已有判断引用的 Evidence 已不可用。",
            risk_notes=("缺少可回查 Evidence。",),
            referenced_agent_argument_ids=(),
            limitations=("Evidence 引用缺失。",),
            created_at=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
        )
    )
    return reader


def _reader_with_industry_relation(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    evidence_store = InMemoryEvidenceStoreClient()
    entity_repository = InMemoryEntityRepository(
        entities={
            "ent_company_002594": EntityRecord(
                entity_id="ent_company_002594",
                entity_type="company",
                name="比亚迪",
                aliases=("002594", "002594.SZ"),
            ),
            "ent_industry_nev": EntityRecord(
                entity_id="ent_industry_nev",
                entity_type="industry",
                name="新能源汽车",
                aliases=("新能源车",),
            ),
        },
        relations=[
            EntityRelationRecord(
                relation_id="rel_002594_nev",
                from_entity_id="ent_company_002594",
                to_entity_id="ent_industry_nev",
                relation_type="belongs_to_industry",
                evidence_ids=("ev_000001",),
            )
        ],
    )
    envelope = _envelope()
    result = evidence_store.ingest_search_result(
        envelope,
        {
            "task_id": "st_industry_test",
            "source": "test",
            "source_type": "report",
            "target": {"ticker": "002594", "entity_id": "ent_industry_nev"},
            "items": [
                {
                    "external_id": "industry_001",
                    "title": "新能源汽车行业跟踪",
                    "content": "政策支持力度较强，供需紧平衡，头部集中度提升。",
                    "ticker": "002594",
                    "entity_ids": ["ent_industry_nev", "ent_company_002594"],
                    "evidence_type": "industry_news",
                    "publish_time": "2026-05-13T00:00:00+00:00",
                }
            ],
        },
    )
    evidence_store.save_structure(
        envelope,
        EvidenceStructureDraft(
            evidence_id=result.created_evidence_ids[0],
            objective_summary="政策支持力度较强，供需紧平衡，头部集中度提升。",
            key_facts=[
                {"name": "policy_support_level", "value": "high"},
                {"name": "policy_support_desc", "value": "政策支持力度较强"},
                {"name": "supply_demand_status", "value": "供需紧平衡"},
                {"name": "competition_landscape", "value": "头部集中度提升"},
            ],
        ),
    )
    return ReportRuntimeReader(
        evidence_store=evidence_store,
        entity_repository=entity_repository,
        agent_repository=InMemoryAgentSwarmRepository(),
        workflow_repository=InMemoryWorkflowRepository(),
        report_repository=repo,
    )


def _reader_with_event_evidence(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    evidence_store = InMemoryEvidenceStoreClient()
    entity_repository = InMemoryEntityRepository(
        entities={
            "ent_company_002594": EntityRecord(
                entity_id="ent_company_002594",
                entity_type="company",
                name="比亚迪",
                aliases=("002594", "002594.SZ"),
            )
        }
    )
    envelope = _envelope()
    result = evidence_store.ingest_search_result(
        envelope,
        {
            "task_id": "st_event_test",
            "source": "test",
            "source_type": "announcement",
            "target": {"ticker": "002594", "entity_id": "ent_company_002594"},
            "items": [
                {
                    "external_id": "event_001",
                    "title": "董事会公告产能规划",
                    "content": "公司董事会公告产能规划，属于客观公告事件。",
                    "ticker": "002594",
                    "entity_ids": ["ent_company_002594"],
                    "evidence_type": "announcement",
                    "publish_time": "2026-05-13T00:00:00+00:00",
                    "source_quality_hint": 0.95,
                    "relevance": 0.95,
                }
            ],
        },
    )
    evidence_store.save_structure(
        envelope,
        EvidenceStructureDraft(
            evidence_id=result.created_evidence_ids[0],
            objective_summary="公司董事会公告产能规划。",
            key_facts=[
                {"name": "event_name", "value": "董事会公告产能规划"},
            ],
        ),
    )
    return ReportRuntimeReader(
        evidence_store=evidence_store,
        entity_repository=entity_repository,
        agent_repository=InMemoryAgentSwarmRepository(),
        workflow_repository=InMemoryWorkflowRepository(),
        report_repository=repo,
    )


def _reader_with_market_snapshot(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    return _reader_with_market_snapshot_draft(
        repo,
        MarketSnapshotDraft(
            snapshot_type="stock_quote",
            ticker="002594",
            entity_ids=("ent_company_002594",),
            source="test",
            snapshot_time="2026-05-13T10:00:00+00:00",
            metrics={
                "stock_code": "002594.SZ",
                "ticker": "002594",
                "name": "比亚迪",
                "price": 218.5,
                "change_rate": 2.15,
                "is_up": True,
                "view_score": 78,
                "view_label": "关注度较高",
            },
        ),
    )


def _reader_with_concept_snapshot(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    return _reader_with_market_snapshot_draft(
        repo,
        MarketSnapshotDraft(
            snapshot_type="concept_heat",
            ticker="LOW_ALTITUDE",
            entity_ids=("ent_concept_low_altitude",),
            source="test",
            snapshot_time="2026-05-13T10:00:00+00:00",
            metrics={
                "concept_name": "低空经济",
                "status": "升温",
                "heat_score": 86,
                "trend": "warming",
                "evidence_ids": ["ev_concept_001"],
            },
        ),
    )


def _reader_with_warning_snapshot(repo: SQLiteReportRunRepository) -> ReportRuntimeReader:
    return _reader_with_market_snapshot_draft(
        repo,
        MarketSnapshotDraft(
            snapshot_type="market_warning",
            ticker="MARKET",
            entity_ids=("ent_concept_low_altitude",),
            source="test",
            snapshot_time="2026-05-13T10:00:00+00:00",
            metrics={
                "warning_id": "warn_001",
                "time": "09:45",
                "title": "异动预警",
                "content": "某板块出现放量上攻",
                "severity": "notice",
                "related_stock_codes": ["002594.SZ"],
                "evidence_ids": ["ev_warning_001"],
            },
        ),
    )


def _reader_with_market_snapshot_draft(
    repo: SQLiteReportRunRepository,
    draft: MarketSnapshotDraft,
) -> ReportRuntimeReader:
    reader = _empty_reader(repo)
    reader.evidence_store.save_market_snapshot(_envelope(), draft)
    return reader


def _envelope() -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="req_report_module_test",
        correlation_id="corr_report_module_test",
        workflow_run_id=None,
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="report_module_test",
        idempotency_key="report_module_test_seed",
    )


def _workflow_run(
    *,
    workflow_run_id: str,
    created_at: datetime,
    entity_id: str,
    stock_code: str,
    ticker: str,
) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        workflow_run_id=workflow_run_id,
        correlation_id=f"corr_{workflow_run_id}",
        ticker=ticker,
        analysis_time=created_at,
        workflow_config_id="cfg_default",
        status="completed",
        stage="completed",
        query=WorkflowQuery(),
        options=WorkflowOptions(),
        entity_id=entity_id,
        stock_code=stock_code,
        created_at=created_at,
        started_at=created_at,
        completed_at=created_at,
        judgment_id=None,
        final_signal=None,
        confidence=None,
        progress=WorkflowProgress(),
    )


class FakeSearchPool:
    def __init__(self, *, task_id: str | None = None, task_ids: tuple[str, ...] = ()) -> None:
        self.task_id = task_id
        self.task_ids = list(task_ids)
        self.calls: list[tuple[InternalCallEnvelope, object]] = []
        self.providers = {"tavily": object(), "exa": object()}

    def submit(self, envelope: InternalCallEnvelope, task: object) -> dict[str, object]:
        self.calls.append((envelope, task))
        task_id = self.task_ids.pop(0) if self.task_ids else self.task_id
        if task_id is None:
            task_id = f"st_fake_{len(self.calls):03d}"
        return {
            "task_id": task_id,
            "status": SearchTaskStatus.QUEUED,
            "accepted_at": datetime.now(timezone.utc),
            "idempotency_key": envelope.idempotency_key or "missing",
            "poll_after_ms": 1000,
        }


class FakeImmediateMarketSearchPool:
    def __init__(self, evidence_store: InMemoryEvidenceStoreClient) -> None:
        self.evidence_store = evidence_store
        self.calls: list[tuple[InternalCallEnvelope, object]] = []
        self.ran_task_ids: list[str] = []
        self.providers = {"akshare": object(), "tavily": object()}
        self.repository = FakeSearchRepository()

    def submit(self, envelope: InternalCallEnvelope, task: object) -> dict[str, object]:
        task_id = "st_intraday_refresh_001"
        self.calls.append((envelope, task))
        self.repository.statuses[task_id] = SearchTaskStatus.QUEUED
        return {
            "task_id": task_id,
            "status": SearchTaskStatus.QUEUED,
            "accepted_at": datetime.now(timezone.utc),
            "idempotency_key": envelope.idempotency_key or "missing",
            "poll_after_ms": 1000,
        }

    def run_task_once(self, task_id: str) -> bool:
        envelope, _ = self.calls[-1]
        self.ran_task_ids.append(task_id)
        self.evidence_store.save_market_snapshot(
            envelope,
            MarketSnapshotDraft(
                snapshot_type="index_quote",
                ticker="000001",
                source="akshare",
                snapshot_time="2026-05-13T09:31:00+00:00",
                metrics={
                    "code": "000001.SH",
                    "name": "上证指数",
                    "value": 3121.5,
                    "open": 3120.1,
                    "high": 3122.0,
                    "low": 3119.8,
                    "previous_close": 3118.2,
                    "intraday_points": [
                        {"time": "09:30", "timestamp": "2026-05-13T09:30:00+08:00", "value": 3120.1},
                        {"time": "09:31", "timestamp": "2026-05-13T09:31:00+08:00", "value": 3121.5},
                    ],
                },
            ),
        )
        self.repository.statuses[task_id] = SearchTaskStatus.COMPLETED
        return True


class FakeSearchRepository:
    def __init__(self) -> None:
        self.statuses: dict[str, SearchTaskStatus] = {}

    def get_task_status(self, task_id: str) -> SearchTaskStatus | None:
        return self.statuses.get(task_id)


class FakeFailedMarketSearchPool:
    def __init__(self) -> None:
        self.calls: list[tuple[InternalCallEnvelope, object]] = []
        self.providers = {"akshare": object()}
        self.repository = FakeSearchRepository()
        self.repository.statuses["st_failed_intraday"] = SearchTaskStatus.FAILED

    def submit(self, envelope: InternalCallEnvelope, task: object) -> dict[str, object]:
        self.calls.append((envelope, task))
        return {
            "task_id": "st_failed_intraday",
            "status": SearchTaskStatus.FAILED,
            "accepted_at": datetime.now(timezone.utc),
            "idempotency_key": envelope.idempotency_key or "missing",
            "poll_after_ms": 1000,
        }

    def run_task_once(self, task_id: str) -> bool:
        return False


class FakeRaisingMarketSearchPool:
    def __init__(self) -> None:
        self.calls: list[tuple[InternalCallEnvelope, object]] = []
        self.providers = {"akshare": object()}
        self.repository = FakeSearchRepository()

    def submit(self, envelope: InternalCallEnvelope, task: object) -> dict[str, object]:
        self.calls.append((envelope, task))
        self.repository.statuses["st_raising_intraday"] = SearchTaskStatus.FAILED
        return {
            "task_id": "st_raising_intraday",
            "status": SearchTaskStatus.QUEUED,
            "accepted_at": datetime.now(timezone.utc),
            "idempotency_key": envelope.idempotency_key or "missing",
            "poll_after_ms": 1000,
        }

    def run_task_once(self, task_id: str) -> bool:
        raise RuntimeError("akshare intraday provider unavailable")
