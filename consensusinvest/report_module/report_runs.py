"""Report run persistence helpers for Report Module views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from consensusinvest.evidence_store.models import EvidenceReferenceBatch
from consensusinvest.runtime import InternalCallEnvelope

from .repository import ReportRunRecord, ReportViewCacheRecord
from .schemas import BenefitsRisksView, ConceptRadarItem, DataState, MarketWarning, ReportMode
from ._utils import _dedupe, _jsonable

def _new_report_run_id(ticker: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"rpt_{today}_{ticker}_{uuid4().hex[:4]}"

def _report_run_id(reader: ReportRuntimeReader, ticker: str) -> str:
    if reader.report_repository is not None:
        return str(reader.report_repository.new_report_run_id(ticker or "0"))
    return _new_report_run_id(ticker or "0")

def _save_benefits_risks_run(
    *,
    reader: ReportRuntimeReader,
    view: BenefitsRisksView,
    report_mode: ReportMode,
    judgment_id: str | None,
) -> None:
    evidence_ids = _dedupe(
        evidence_id
        for item in [*view.benefits, *view.risks]
        for evidence_id in item.evidence_ids
    )
    _save_report_run(
        reader=reader,
        report_run_id=view.report_run_id,
        ticker=view.ticker,
        stock_code=view.stock_code,
        report_mode=report_mode,
        data_state=DataState.READY if view.benefits or view.risks or view.workflow_run_id else DataState.MISSING,
        workflow_run_id=view.workflow_run_id,
        judgment_id=judgment_id,
        entity_id=None,
        input_refs=_input_refs(
            evidence_ids=evidence_ids,
            market_snapshot_ids=[],
            workflow_run_id=view.workflow_run_id,
            judgment_id=judgment_id,
        ),
        output_snapshot=_jsonable(view),
        limitations=_stock_limitations(report_mode),
        refresh_task_id=None,
    )

def _save_report_run(
    *,
    reader: ReportRuntimeReader,
    report_run_id: str,
    ticker: str,
    stock_code: str | None,
    report_mode: ReportMode,
    data_state: DataState,
    workflow_run_id: str | None,
    judgment_id: str | None,
    entity_id: str | None,
    input_refs: dict[str, Any],
    output_snapshot: dict[str, Any],
    limitations: list[str],
    refresh_task_id: str | None,
) -> None:
    if reader.report_repository is None:
        return
    now = datetime.now(timezone.utc)
    status = _report_run_status(data_state)
    run = reader.report_repository.create_run(
        ReportRunRecord(
            report_run_id=report_run_id,
            ticker=ticker,
            stock_code=stock_code,
            status=status,
            report_mode=report_mode.value,
            data_state=data_state.value,
            input_refs=input_refs,
            output_snapshot=output_snapshot,
            limitations=limitations,
            created_at=now,
            updated_at=now,
            workflow_run_id=workflow_run_id,
            judgment_id=judgment_id,
            entity_id=entity_id,
            refresh_task_id=refresh_task_id,
            started_at=now,
            completed_at=now if status == "completed" else None,
        )
    )
    upsert_cache = getattr(reader.report_repository, "upsert_view_cache", None)
    if callable(upsert_cache):
        upsert_cache(_cache_record_from_run(run))
    _save_report_view_references(reader=reader, report_run_id=run.report_run_id, input_refs=run.input_refs)

def _save_report_view_references(
    *,
    reader: ReportRuntimeReader,
    report_run_id: str,
    input_refs: dict[str, Any],
) -> None:
    evidence_ids = _dedupe(str(evidence_id) for evidence_id in input_refs.get("evidence_ids", []) if evidence_id)
    if not evidence_ids:
        return
    reader.evidence_store.save_references(
        InternalCallEnvelope(
            request_id=f"req_report_refs_{report_run_id}",
            correlation_id=f"corr_report_refs_{report_run_id}",
            workflow_run_id=None,
            analysis_time=datetime.now(timezone.utc),
            requested_by="report_module",
            idempotency_key=f"report_view_refs_{report_run_id}",
        ),
        EvidenceReferenceBatch(
            source_type="report_view",
            source_id=report_run_id,
            references=[
                {"evidence_id": evidence_id, "reference_role": "cited"}
                for evidence_id in evidence_ids
            ],
        ),
    )

def _cache_record_from_run(run: ReportRunRecord) -> ReportViewCacheRecord:
    return ReportViewCacheRecord(
        cache_key=run.report_run_id,
        report_run_id=run.report_run_id,
        report_mode=run.report_mode,
        input_refs=run.input_refs,
        output_snapshot=run.output_snapshot,
        limitations=run.limitations,
        data_state=run.data_state,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )

def _save_market_list_run(
    *,
    reader: ReportRuntimeReader,
    ticker: str,
    items: list[ConceptRadarItem] | list[MarketWarning],
    data_state: DataState,
) -> None:
    output_items = [_jsonable(item) for item in items]
    _save_report_run(
        reader=reader,
        report_run_id=_report_run_id(reader, ticker),
        ticker=ticker,
        stock_code=None,
        report_mode=ReportMode.REPORT_GENERATION,
        data_state=data_state,
        workflow_run_id=None,
        judgment_id=None,
        entity_id=None,
        input_refs=_input_refs(
            evidence_ids=_dedupe(evidence_id for item in items for evidence_id in item.evidence_ids),
            market_snapshot_ids=_dedupe(snapshot_id for item in items for snapshot_id in item.snapshot_ids),
            workflow_run_id=None,
            judgment_id=None,
        ),
        output_snapshot={
            "items": output_items,
            "data_state": data_state.value,
        },
        limitations=_market_limitations(),
        refresh_task_id=None,
    )

def _report_run_status(data_state: DataState) -> str:
    if data_state in {DataState.PENDING_REFRESH, DataState.REFRESHING}:
        return data_state.value
    return "completed"

def _input_refs(
    *,
    evidence_ids: Iterable[str],
    market_snapshot_ids: Iterable[str],
    workflow_run_id: str | None,
    judgment_id: str | None,
) -> dict[str, Any]:
    return {
        "evidence_ids": _dedupe(evidence_ids),
        "market_snapshot_ids": _dedupe(market_snapshot_ids),
        "workflow_run_id": workflow_run_id,
        "judgment_id": judgment_id,
    }

def _stock_limitations(report_mode: ReportMode) -> list[str]:
    if report_mode == ReportMode.WITH_WORKFLOW_TRACE:
        return ["本报告视图仅投影已入库主 workflow、Judgment 与 Evidence 引用，不生成新的投资判断。"]
    return ["本报告未运行主 workflow，因此没有 Agent Swarm 论证链和 Judge 最终判断。"]

def _market_limitations() -> list[str]:
    return ["市场视图仅投影已入库 MarketSnapshot 和引用信息，不构成投资建议。"]
