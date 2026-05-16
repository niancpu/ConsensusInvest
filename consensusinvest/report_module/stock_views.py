"""Stock-oriented Report Module view builders."""

from __future__ import annotations

from consensusinvest.common.errors import NotFoundError, ValidationError
from consensusinvest.evidence_store.models import EvidenceDetail

from .runtime_reader import ReportRuntimeReader
from ._utils import _dedupe, _dt, _jsonable, _now_iso
from .evidence_projection import (
    _event_evidence,
    _event_level,
    _event_name,
    _event_score,
    _industry_evidence,
    _industry_relation,
    _industry_text,
    _policy_support_level,
    _required_stock,
    _risk_disclosures,
    _selected_judgment,
    _summary,
)
from .projections import _action_label, _exchange, _stock_code, _ticker
from .refresh import _request_stock_refresh
from .report_runs import (
    _input_refs,
    _report_run_id,
    _save_benefits_risks_run,
    _save_report_run,
    _stock_limitations,
)
from .schemas import (
    ActionView,
    BenefitItem,
    BenefitsRisksView,
    DataState,
    EventImpactItem,
    EventImpactRankingView,
    EvidenceMatch,
    IndustryDetailsView,
    IndustryLinks,
    KeyEvidence,
    ReportBody,
    RefreshPolicy,
    ReportMode,
    RiskItem,
    SearchMatch,
    Signal,
    StockAnalysisView,
    StockLinks,
    StockSearchHit,
    TraceRefs,
)



def build_stock_search(
    *,
    reader: ReportRuntimeReader,
    keyword: str,
    limit: int,
    include_evidence: bool,
) -> tuple[list[StockSearchHit], DataState]:
    if not keyword or not keyword.strip():
        raise ValidationError("Query parameter `keyword` must not be empty.")
    if limit < 1 or limit > 50:
        raise ValidationError("Query parameter `limit` must be between 1 and 50.")

    entities = reader.search_entities(keyword, limit=limit)
    evidence_hits = reader.evidence_for_keyword(keyword, limit=limit * 2)
    evidence_by_entity: dict[str, list[EvidenceDetail]] = {}
    for detail in evidence_hits:
        for entity_id in detail.evidence.entity_ids:
            evidence_by_entity.setdefault(entity_id, []).append(detail)

    hits: list[StockSearchHit] = []
    for entity in entities:
        stock_code = _stock_code(entity)
        ticker = _ticker(entity)
        exchange = _exchange(stock_code)
        if stock_code is None or ticker is None:
            continue
        evidence_for_entity = evidence_by_entity.get(entity.entity_id, [])
        matched_fields = ["name"]
        if keyword.lower() in stock_code.lower() or keyword.lower() in ticker.lower():
            matched_fields.append("ticker")
        if evidence_for_entity:
            matched_fields.append("evidence_title")

        evidence_payload: list[EvidenceMatch] = []
        if include_evidence:
            for detail in evidence_for_entity[:3]:
                item = detail.evidence
                evidence_payload.append(
                    EvidenceMatch(
                        evidence_id=item.evidence_id,
                        title=item.title or item.evidence_id,
                        objective_summary=_summary(detail),
                        published_at=_dt(item.publish_time),
                        source_quality=item.source_quality or 0.0,
                    )
                )

        hits.append(
            StockSearchHit(
                stock_code=stock_code,
                ticker=ticker,
                exchange=exchange,
                name=entity.name,
                market="A_SHARE",
                entity_id=entity.entity_id,
                aliases=list(entity.aliases),
                match=SearchMatch(
                    type="entity_and_evidence" if evidence_for_entity else "entity",
                    score=0.92 if evidence_for_entity else 0.85,
                    matched_fields=matched_fields,
                ),
                evidence_matches=evidence_payload,
            )
        )

    return hits, DataState.READY if hits else DataState.MISSING



def build_stock_analysis_view(
    *,
    reader: ReportRuntimeReader,
    stock_code: str,
    query: str | None,
    workflow_run_id: str | None,
    latest: bool,
    refresh: RefreshPolicy,
) -> tuple[StockAnalysisView, str | None]:
    entity = _required_stock(reader, stock_code)
    ticker = _ticker(entity) or ""
    report_run_id = _report_run_id(reader, ticker)
    judgment = _selected_judgment(reader, entity, workflow_run_id=workflow_run_id, latest=latest)
    evidence_records = reader.evidence_for_entity(entity.entity_id, limit=5)
    has_workflow = judgment is not None

    action: ActionView | None = None
    risks: list[RiskItem] = []
    summary_text = ""
    if judgment is not None:
        action = ActionView(
            label=_action_label(judgment.final_signal),
            signal=Signal(judgment.final_signal),
            reason=judgment.reasoning,
            source="main_judgment_summary",
        )
        risks = [
            RiskItem(text=text, evidence_ids=list(judgment.key_negative_evidence_ids), source="main_judgment_summary")
            for text in judgment.risk_notes
        ]
        summary_text = judgment.reasoning
    else:
        risks = _risk_disclosures(evidence_records)
        summary_text = "；".join(_summary(detail) for detail in evidence_records[:3] if _summary(detail).strip())

    key_evidence = [
        KeyEvidence(
            evidence_id=detail.evidence.evidence_id,
            title=detail.evidence.title or detail.evidence.evidence_id,
            objective_summary=_summary(detail),
            publish_time=_dt(detail.evidence.publish_time),
            fetched_at=_dt(detail.evidence.fetched_at),
            source_quality=detail.evidence.source_quality or 0.0,
            relevance=detail.evidence.relevance or 0.0,
        )
        for detail in evidence_records
    ]

    evidence_ids = _dedupe(detail.evidence.evidence_id for detail in evidence_records)
    if judgment is not None:
        evidence_ids = _dedupe(
            [*evidence_ids, *judgment.key_positive_evidence_ids, *judgment.key_negative_evidence_ids]
        )

    data_state = DataState.READY if evidence_records or judgment is not None else DataState.MISSING
    refresh_task_id = None
    if data_state == DataState.MISSING and refresh in {RefreshPolicy.MISSING, RefreshPolicy.STALE}:
        refresh_task_id = _request_stock_refresh(
            reader=reader,
            entity=entity,
            ticker=ticker,
            stock_code=_stock_code(entity) or stock_code,
            query=query,
            report_run_id=report_run_id,
        )
        if refresh_task_id is not None:
            data_state = DataState.REFRESHING

    view = StockAnalysisView(
        stock_code=_stock_code(entity) or stock_code,
        ticker=ticker,
        stock_name=entity.name,
        entity_id=entity.entity_id,
        workflow_run_id=judgment.workflow_run_id if judgment else None,
        judgment_id=judgment.judgment_id if judgment else None,
        report_run_id=report_run_id,
        report_mode=ReportMode.WITH_WORKFLOW_TRACE if has_workflow else ReportMode.REPORT_GENERATION,
        data_state=data_state,
        action=action,
        report=ReportBody(
            title="个股研究聚合视图",
            summary=summary_text,
            key_evidence=key_evidence,
            risks=risks,
        ),
        trace_refs=TraceRefs(
            evidence_ids=evidence_ids,
            market_snapshot_ids=[],
            workflow_run_id=judgment.workflow_run_id if judgment else None,
            judgment_id=judgment.judgment_id if judgment else None,
        ),
        links=StockLinks(
            entity=f"/api/v1/entities/{entity.entity_id}",
            workflow_run=f"/api/v1/workflow-runs/{judgment.workflow_run_id}" if judgment else None,
            trace=f"/api/v1/workflow-runs/{judgment.workflow_run_id}/trace" if judgment else None,
            judgment=f"/api/v1/judgments/{judgment.judgment_id}" if judgment else None,
        ),
        updated_at=_dt(judgment.created_at) if judgment else _now_iso(),
    )
    output_snapshot = _jsonable(view)
    if refresh_task_id is not None:
        output_snapshot["refresh_task_id"] = refresh_task_id
    _save_report_run(
        reader=reader,
        report_run_id=view.report_run_id,
        ticker=ticker,
        stock_code=view.stock_code,
        report_mode=view.report_mode,
        data_state=view.data_state,
        workflow_run_id=view.workflow_run_id,
        judgment_id=view.judgment_id,
        entity_id=view.entity_id,
        input_refs=_input_refs(
            evidence_ids=view.trace_refs.evidence_ids,
            market_snapshot_ids=view.trace_refs.market_snapshot_ids,
            workflow_run_id=view.workflow_run_id,
            judgment_id=view.judgment_id,
        ),
        output_snapshot=output_snapshot,
        limitations=_stock_limitations(view.report_mode),
        refresh_task_id=refresh_task_id,
        input_snapshot={
            "view": "stock_analysis",
            "stock_code": stock_code,
            "query": query,
            "workflow_run_id": workflow_run_id,
            "latest": latest,
            "refresh": refresh.value,
        },
    )
    return view, refresh_task_id



def build_industry_details_view(
    *,
    reader: ReportRuntimeReader,
    stock_code: str,
    workflow_run_id: str | None,
) -> IndustryDetailsView:
    entity = _required_stock(reader, stock_code)
    industry_relation, industry = _industry_relation(reader, entity)
    if industry_relation is None or industry is None:
        raise NotFoundError(
            f"Industry mapping not found for stock {stock_code}.",
            code="INDUSTRY_MAPPING_NOT_FOUND",
            details={"stock_code": stock_code},
        )

    evidence_records = _industry_evidence(reader, entity, industry_relation, industry, workflow_run_id=workflow_run_id)
    policy_support_level = _policy_support_level(evidence_records)
    report_run_id = _report_run_id(reader, _ticker(entity) or "")
    view = IndustryDetailsView(
        stock_code=_stock_code(entity) or stock_code,
        ticker=_ticker(entity) or "",
        report_run_id=report_run_id,
        industry_entity_id=industry.entity_id,
        industry_name=industry.name,
        policy_support_level=policy_support_level,
        policy_support_desc=_industry_text(
            evidence_records,
            fact_names=("policy_support_desc", "policy_support", "政策支持", "政策支持描述"),
            keywords=("政策", "支持", "补贴", "规划"),
            fallback="未从已入库 Evidence 读取到明确政策支持描述。",
        ),
        supply_demand_status=_industry_text(
            evidence_records,
            fact_names=("supply_demand_status", "supply_demand", "供需状态", "供需"),
            keywords=("供需", "需求", "产能", "库存", "交付", "销量"),
            fallback="未从已入库 Evidence 读取到明确供需状态。",
        ),
        competition_landscape=_industry_text(
            evidence_records,
            fact_names=("competition_landscape", "competition", "竞争格局", "竞争"),
            keywords=("竞争", "格局", "份额", "集中", "对手"),
            fallback="未从已入库 Evidence 读取到明确竞争格局。",
        ),
        referenced_evidence_ids=_dedupe(detail.evidence.evidence_id for detail in evidence_records),
        market_snapshot_ids=[],
        links=IndustryLinks(
            entity=f"/api/v1/entities/{industry.entity_id}",
            entity_relations=f"/api/v1/entities/{industry.entity_id}/relations",
        ),
        updated_at=_now_iso(),
    )
    _save_report_run(
        reader=reader,
        report_run_id=report_run_id,
        ticker=view.ticker,
        stock_code=view.stock_code,
        report_mode=ReportMode.WITH_WORKFLOW_TRACE if workflow_run_id else ReportMode.REPORT_GENERATION,
        data_state=DataState.READY if view.referenced_evidence_ids or view.market_snapshot_ids else DataState.MISSING,
        workflow_run_id=workflow_run_id,
        judgment_id=None,
        entity_id=entity.entity_id,
        input_refs=_input_refs(
            evidence_ids=view.referenced_evidence_ids,
            market_snapshot_ids=view.market_snapshot_ids,
            workflow_run_id=workflow_run_id,
            judgment_id=None,
        ),
        output_snapshot=_jsonable(view),
        limitations=_stock_limitations(
            ReportMode.WITH_WORKFLOW_TRACE if workflow_run_id else ReportMode.REPORT_GENERATION
        ),
        refresh_task_id=None,
        input_snapshot={
            "view": "industry_details",
            "stock_code": stock_code,
            "workflow_run_id": workflow_run_id,
        },
    )
    return view



def build_event_impact_ranking(
    *,
    reader: ReportRuntimeReader,
    stock_code: str,
    workflow_run_id: str | None,
    limit: int,
) -> EventImpactRankingView:
    if limit < 1 or limit > 50:
        raise ValidationError("Query parameter `limit` must be between 1 and 50.")
    entity = _required_stock(reader, stock_code)
    evidence_records = _event_evidence(reader, entity, workflow_run_id=workflow_run_id, limit=limit)
    report_run_id = _report_run_id(reader, _ticker(entity) or "")
    view = EventImpactRankingView(
        stock_code=_stock_code(entity) or stock_code,
        ticker=_ticker(entity) or "",
        report_run_id=report_run_id,
        ranker="report_event_impact_ranker_v1",
        items=[
            EventImpactItem(
                event_name=_event_name(detail),
                impact_score=_event_score(detail),
                impact_level=_event_level(_event_score(detail)),
                direction=None,
                evidence_ids=[detail.evidence.evidence_id],
                workflow_run_id=workflow_run_id,
                judgment_id=None,
            )
            for detail in evidence_records
        ],
        updated_at=_now_iso(),
    )
    _save_report_run(
        reader=reader,
        report_run_id=report_run_id,
        ticker=view.ticker,
        stock_code=view.stock_code,
        report_mode=ReportMode.WITH_WORKFLOW_TRACE if workflow_run_id else ReportMode.REPORT_GENERATION,
        data_state=DataState.READY if view.items else DataState.MISSING,
        workflow_run_id=workflow_run_id,
        judgment_id=None,
        entity_id=entity.entity_id,
        input_refs=_input_refs(
            evidence_ids=_dedupe(evidence_id for item in view.items for evidence_id in item.evidence_ids),
            market_snapshot_ids=[],
            workflow_run_id=workflow_run_id,
            judgment_id=None,
        ),
        output_snapshot=_jsonable(view),
        limitations=_stock_limitations(
            ReportMode.WITH_WORKFLOW_TRACE if workflow_run_id else ReportMode.REPORT_GENERATION
        ),
        refresh_task_id=None,
        input_snapshot={
            "view": "event_impact_ranking",
            "stock_code": stock_code,
            "workflow_run_id": workflow_run_id,
            "limit": limit,
        },
    )
    return view



def build_benefits_risks_view(
    *,
    reader: ReportRuntimeReader,
    stock_code: str,
    workflow_run_id: str | None,
) -> BenefitsRisksView:
    entity = _required_stock(reader, stock_code)
    judgment = _selected_judgment(reader, entity, workflow_run_id=workflow_run_id, latest=True)
    ticker = _ticker(entity) or ""
    if judgment is None:
        risks = _risk_disclosures(reader.evidence_for_entity(entity.entity_id))
        view = BenefitsRisksView(
            stock_code=_stock_code(entity) or stock_code,
            ticker=ticker,
            workflow_run_id=None,
            report_run_id=_report_run_id(reader, ticker),
            benefits=[],
            risks=risks,
            updated_at=_now_iso(),
        )
        _save_benefits_risks_run(reader=reader, view=view, report_mode=ReportMode.REPORT_GENERATION, judgment_id=None)
        return view

    benefits = [
        BenefitItem(
            text=judgment.reasoning,
            evidence_ids=list(judgment.key_positive_evidence_ids),
            source="main_judgment_summary",
        )
    ] if judgment.key_positive_evidence_ids or judgment.reasoning else []
    risks = [
        RiskItem(text=text, evidence_ids=list(judgment.key_negative_evidence_ids), source="main_judgment_summary")
        for text in judgment.risk_notes
    ]
    view = BenefitsRisksView(
        stock_code=_stock_code(entity) or stock_code,
        ticker=ticker,
        workflow_run_id=judgment.workflow_run_id,
        report_run_id=_report_run_id(reader, ticker),
        benefits=benefits,
        risks=risks,
        updated_at=_dt(judgment.created_at),
    )
    _save_benefits_risks_run(
        reader=reader,
        view=view,
        report_mode=ReportMode.WITH_WORKFLOW_TRACE,
        judgment_id=judgment.judgment_id,
    )
    return view
