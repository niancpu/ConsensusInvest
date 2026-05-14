from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from consensusinvest.report_module.repository import (
    ReportRunRecord,
    ReportViewCacheRecord,
    SQLiteReportRunRepository,
)


def _record(
    repo: SQLiteReportRunRepository,
    *,
    ticker: str = "002594",
    stock_code: str = "002594.SZ",
    entity_id: str | None = "ent_company_002594",
    status: str = "queued",
    created_at: datetime,
) -> ReportRunRecord:
    return ReportRunRecord(
        report_run_id=repo.new_report_run_id(ticker, created_at=created_at),
        ticker=ticker,
        stock_code=stock_code,
        status=status,
        report_mode="report_generation",
        data_state="missing",
        workflow_run_id=None,
        judgment_id=None,
        entity_id=entity_id,
        input_refs={
            "workflow_run_id": None,
            "judgment_id": None,
            "evidence_ids": ["ev_20260513_002594_001"],
            "market_snapshot_ids": ["mkt_snap_20260513_002594"],
        },
        output_snapshot={},
        limitations=["未运行主 workflow，因此没有 Judge 最终判断。"],
        created_at=created_at,
        updated_at=created_at,
    )


def test_creates_updates_and_reopens_report_runs(tmp_path: Path) -> None:
    created_at = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "report_runs.sqlite3"

    repo = SQLiteReportRunRepository(db_path)
    queued = repo.create_run(_record(repo, status="queued", created_at=created_at))
    running = repo.update_run(
        queued.report_run_id,
        status="running",
        data_state="refreshing",
        refresh_task_id="st_20260513_000001",
        started_at=created_at,
        updated_at=created_at,
    )
    completed = repo.update_run(
        running.report_run_id,
        status="completed",
        data_state="ready",
        output_snapshot={
            "summary": "报告视图基于已入库 Evidence 和 MarketSnapshot 生成。",
            "risks": [
                {
                    "text": "现金流质量需要继续核对。",
                    "evidence_ids": ["ev_20260513_002594_001"],
                    "source": "evidence_structure_risk_disclosure",
                }
            ],
        },
        details={"assembler_id": "report_view_assembler_v1"},
        completed_at=created_at,
        updated_at=created_at,
    )
    repo.close()

    reopened = SQLiteReportRunRepository(db_path)
    restored = reopened.get_run(completed.report_run_id)

    assert restored == completed
    assert restored is not None
    assert restored.report_run_id == "rpt_20260513_002594_0001"
    assert restored.workflow_run_id is None
    assert restored.judgment_id is None
    assert restored.entity_id == "ent_company_002594"
    assert restored.input_refs["evidence_ids"] == ["ev_20260513_002594_001"]
    assert restored.input_refs["market_snapshot_ids"] == ["mkt_snap_20260513_002594"]
    assert restored.output_snapshot["risks"][0]["source"] == "evidence_structure_risk_disclosure"
    assert restored.refresh_task_id == "st_20260513_000001"
    assert reopened.new_report_run_id("002594", created_at=created_at) == "rpt_20260513_002594_0002"
    reopened.close()


def test_upserts_lists_and_reopens_report_view_cache(tmp_path: Path) -> None:
    created_at = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 5, 13, 11, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "report_runs.sqlite3"

    repo = SQLiteReportRunRepository(db_path)
    run = repo.create_run(_record(repo, status="completed", created_at=created_at))
    created = repo.upsert_view_cache(
        ReportViewCacheRecord(
            cache_key=run.report_run_id,
            report_run_id=run.report_run_id,
            report_mode=run.report_mode,
            input_refs=run.input_refs,
            output_snapshot={"summary": "initial"},
            limitations=run.limitations,
            data_state="missing",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    updated = repo.upsert_view_cache(
        ReportViewCacheRecord(
            cache_key=run.report_run_id,
            report_run_id=run.report_run_id,
            report_mode="with_workflow_trace",
            input_refs={**run.input_refs, "judgment_id": "jdg_001"},
            output_snapshot={"summary": "updated", "report_run_id": run.report_run_id},
            limitations=["updated limitation"],
            data_state="ready",
            created_at=created.created_at,
            updated_at=updated_at,
        )
    )
    repo.close()

    reopened = SQLiteReportRunRepository(db_path)
    restored = reopened.get_view_cache(run.report_run_id)

    assert restored == updated
    assert restored is not None
    assert restored.cache_key == run.report_run_id
    assert restored.report_run_id == run.report_run_id
    assert restored.report_mode == "with_workflow_trace"
    assert restored.input_refs["judgment_id"] == "jdg_001"
    assert restored.output_snapshot["summary"] == "updated"
    assert restored.limitations == ["updated limitation"]
    assert reopened.list_view_cache(limit=1) == [updated]
    assert reopened.get_run(run.report_run_id) == run
    reopened.close()


def test_lists_with_stock_status_filters_and_pagination(tmp_path: Path) -> None:
    created_at = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    repo = SQLiteReportRunRepository(tmp_path / "report_runs.sqlite3")

    first = repo.create_run(_record(repo, ticker="002594", stock_code="002594.SZ", status="completed", created_at=created_at))
    second = repo.create_run(_record(repo, ticker="002594", stock_code="002594.SZ", status="running", created_at=created_at.replace(hour=11)))
    third = repo.create_run(_record(repo, ticker="000001", stock_code="000001.SZ", status="completed", created_at=created_at.replace(hour=12)))

    assert [run.report_run_id for run in repo.list_runs(limit=2)] == [
        third.report_run_id,
        second.report_run_id,
    ]
    assert [run.report_run_id for run in repo.list_runs(limit=1, offset=1)] == [second.report_run_id]
    assert [run.report_run_id for run in repo.list_runs(stock_code="002594.SZ")] == [
        second.report_run_id,
        first.report_run_id,
    ]
    assert [run.report_run_id for run in repo.list_runs(status="completed")] == [
        third.report_run_id,
        first.report_run_id,
    ]
    assert repo.count_runs(stock_code="002594.SZ") == 2
    assert repo.count_runs(status="completed") == 2
    repo.close()
