"""Report Module view assembler service.

This layer is the "Report View Assembler" described in
`docs/internal_contracts/report_module.md` §4. It only does sorting, excerpting,
template filling and reference organization. It must NOT generate investment
interpretation, conclusions or actions.

Key boundary rules enforced here:

- When `judgment_id` is null → `action` and `benefits` are empty; `risks` may
  only come from Evidence Structure risk disclosures.
- `report_generation` mode → `workflow_run_id` and `judgment_id` are null.
- Every textual field on the view must carry a traceable reference
  (`evidence_ids`, `market_snapshot_ids`, `workflow_run_id`, `judgment_id`).
- `data_state=pending_refresh` only signals that a SearchTask was queued, not
  that fresh data is in this response.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from ..common.errors import NotFoundError, ValidationError
from . import repository as repo
from .schemas import (
    ActionView,
    BenefitItem,
    BenefitsRisksView,
    ConceptRadarItem,
    DataState,
    EventImpactItem,
    EventImpactRankingView,
    EvidenceMatch,
    IndexOverview,
    IndexQuote,
    IndustryDetailsView,
    IndustryLinks,
    KeyEvidence,
    MarketSentiment,
    MarketStockRow,
    MarketStocksList,
    MarketStocksPagination,
    MarketWarning,
    RefreshPolicy,
    ReportBody,
    ReportMode,
    RiskItem,
    SearchMatch,
    Signal,
    StockAnalysisView,
    StockLinks,
    StockSearchHit,
    TraceRefs,
)


def _new_report_run_id(ticker: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"rpt_{today}_{ticker}_{uuid4().hex[:4]}"


def _new_refresh_task_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"st_{today}_{uuid4().hex[:8]}"


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item not in seen:
            seen[item] = None
    return list(seen.keys())


# -- Stock search ----------------------------------------------------------


def build_stock_search(
    *,
    keyword: str,
    limit: int,
    include_evidence: bool,
) -> tuple[list[StockSearchHit], DataState]:
    if not keyword or not keyword.strip():
        raise ValidationError("Query parameter `keyword` must not be empty.")
    if limit < 1 or limit > 50:
        raise ValidationError("Query parameter `limit` must be between 1 and 50.")

    entities = repo.search_entities(keyword, limit=limit)
    evidence_hits = repo.search_evidence_by_keyword(keyword, limit=limit * 2)
    evidence_by_entity: dict[str, list[repo.EvidenceRecord]] = {}
    for evidence in evidence_hits:
        evidence_by_entity.setdefault(evidence.entity_id, []).append(evidence)

    hits: list[StockSearchHit] = []
    for entity in entities:
        if entity.stock_code is None:
            continue  # only companies are stock-search results
        matched_fields = ["name"]
        if keyword.lower() in (entity.stock_code or "").lower():
            matched_fields.append("ticker")
        evidence_for_entity = evidence_by_entity.get(entity.entity_id, [])
        if evidence_for_entity:
            matched_fields.append("evidence_title")

        if evidence_for_entity and entity.entity_id in evidence_by_entity:
            match_type = "entity_and_evidence"
            score = 0.92
        else:
            match_type = "entity"
            score = 0.85

        evidence_payload: list[EvidenceMatch] = []
        if include_evidence:
            for ev in evidence_for_entity[:3]:
                evidence_payload.append(
                    EvidenceMatch(
                        evidence_id=ev.evidence_id,
                        title=ev.title,
                        objective_summary=ev.objective_summary,
                        published_at=ev.published_at,
                        source_quality=ev.source_quality,
                    )
                )

        hits.append(
            StockSearchHit(
                stock_code=entity.stock_code,
                ticker=entity.ticker or "",
                exchange=entity.exchange or "",
                name=entity.name,
                market=entity.market or "A_SHARE",
                entity_id=entity.entity_id,
                aliases=list(entity.aliases),
                match=SearchMatch(type=match_type, score=score, matched_fields=matched_fields),
                evidence_matches=evidence_payload,
            )
        )

    data_state = DataState.READY if hits else DataState.PARTIAL
    return hits, data_state


# -- Stock analysis aggregation view --------------------------------------


def build_stock_analysis_view(
    *,
    stock_code: str,
    query: str | None,
    workflow_run_id: str | None,
    latest: bool,
    refresh: RefreshPolicy,
) -> StockAnalysisView:
    entity = repo.find_entity_by_stock_code(stock_code)
    if entity is None or entity.stock_code is None:
        raise NotFoundError(f"Stock not found: {stock_code}", details={"stock_code": stock_code})

    judgment = None
    if workflow_run_id:
        judgment = repo.get_judgment_by_workflow(workflow_run_id)
        if judgment is None:
            raise NotFoundError(
                f"Workflow run not found: {workflow_run_id}",
                details={"workflow_run_id": workflow_run_id},
                code="WORKFLOW_NOT_FOUND",
            )
    elif latest:
        judgment = repo.latest_judgment_for_entity(entity.entity_id)

    evidence_records = repo.evidence_for_entity(entity.entity_id, limit=5)
    snapshot_ids: list[str] = []
    if judgment is not None:
        snapshot_ids = list(judgment.market_snapshot_ids)

    has_workflow = judgment is not None
    report_mode = ReportMode.WITH_WORKFLOW_TRACE if has_workflow else ReportMode.REPORT_GENERATION

    # Boundary rule: action / benefits only when a Judgment exists.
    action: ActionView | None = None
    benefits: list[BenefitItem] = []
    risks: list[RiskItem] = []
    summary_text: str
    title = "个股研究聚合视图"
    if has_workflow and judgment is not None:
        action = ActionView(
            label=judgment.action_label,
            signal=Signal(judgment.action_signal),
            reason=judgment.action_reason,
            source="main_judgment_summary",
        )
        benefits = [BenefitItem(**item) for item in judgment.benefits]
        risks = [RiskItem(**item) for item in judgment.risks]
        summary_text = judgment.summary
    else:
        # report_generation mode — summary is a template over already-stored objects.
        summary_text = (
            "报告视图基于已入库 Evidence Structure 与 MarketSnapshot 拼装，"
            "未运行主 workflow；不含 Agent Swarm 论证或 Judge 结论。"
        )
        # Risks may surface only from evidence already tagged risk_disclosure.
        risks = [
            RiskItem(
                text=e.objective_summary,
                evidence_ids=[e.evidence_id],
                source="evidence_structure_risk_disclosure",
            )
            for e in evidence_records
            if "risk_disclosure" in e.tags
        ]

    key_evidence = [
        KeyEvidence(
            evidence_id=e.evidence_id,
            title=e.title,
            objective_summary=e.objective_summary,
            source_quality=e.source_quality,
            relevance=e.relevance,
        )
        for e in evidence_records
    ]

    evidence_ids = _dedupe(e.evidence_id for e in evidence_records)
    if judgment is not None:
        evidence_ids = _dedupe([*evidence_ids, *judgment.key_evidence_ids])

    trace_refs = TraceRefs(
        evidence_ids=evidence_ids,
        market_snapshot_ids=snapshot_ids,
        workflow_run_id=judgment.workflow_run_id if judgment else None,
        judgment_id=judgment.judgment_id if judgment else None,
    )

    links = StockLinks(
        entity=f"/api/v1/entities/{entity.entity_id}",
        workflow_run=f"/api/v1/workflow-runs/{judgment.workflow_run_id}" if judgment else None,
        trace=f"/api/v1/workflow-runs/{judgment.workflow_run_id}/trace" if judgment else None,
        judgment=f"/api/v1/judgments/{judgment.judgment_id}" if judgment else None,
    )

    data_state = DataState.READY
    if not evidence_records and refresh in {RefreshPolicy.MISSING, RefreshPolicy.STALE}:
        data_state = DataState.PENDING_REFRESH

    # query is purely a hint for view assembly; never used as a fact source.
    _ = query  # acknowledged-and-ignored

    return StockAnalysisView(
        stock_code=entity.stock_code,
        ticker=entity.ticker or "",
        stock_name=entity.name,
        entity_id=entity.entity_id,
        workflow_run_id=judgment.workflow_run_id if judgment else None,
        judgment_id=judgment.judgment_id if judgment else None,
        report_run_id=_new_report_run_id(entity.ticker or "0"),
        report_mode=report_mode,
        data_state=data_state,
        action=action,
        report=ReportBody(
            title=title,
            summary=summary_text,
            key_evidence=key_evidence,
            risks=risks,
        ),
        trace_refs=trace_refs,
        links=links,
        updated_at=judgment.updated_at if judgment else repo.now_iso(),
    )


# -- Industry details ------------------------------------------------------


def build_industry_details_view(
    *,
    stock_code: str,
    workflow_run_id: str | None,
) -> IndustryDetailsView:
    entity = repo.find_entity_by_stock_code(stock_code)
    if entity is None or entity.stock_code is None:
        raise NotFoundError(f"Stock not found: {stock_code}", details={"stock_code": stock_code})

    industry = repo.get_industry_for_entity(entity.entity_id)
    if industry is None:
        raise NotFoundError(
            f"Industry mapping not found for stock {stock_code}.",
            details={"stock_code": stock_code},
        )

    # workflow_run_id is accepted as a filter hint but doesn't override industry mapping.
    _ = workflow_run_id

    return IndustryDetailsView(
        stock_code=entity.stock_code,
        ticker=entity.ticker or "",
        industry_entity_id=industry.entity_id,
        industry_name=industry.name,
        policy_support_level=industry.policy_support_level,  # type: ignore[arg-type]
        policy_support_desc=industry.policy_support_desc,
        supply_demand_status=industry.supply_demand_status,
        competition_landscape=industry.competition_landscape,
        referenced_evidence_ids=list(industry.referenced_evidence_ids),
        market_snapshot_ids=list(industry.market_snapshot_ids),
        links=IndustryLinks(
            entity=f"/api/v1/entities/{industry.entity_id}",
            entity_relations=f"/api/v1/entities/{industry.entity_id}/relations",
        ),
        updated_at=industry.updated_at,
    )


# -- Event impact ranking --------------------------------------------------


def build_event_impact_ranking(
    *,
    stock_code: str,
    workflow_run_id: str | None,
    limit: int,
) -> EventImpactRankingView:
    if limit < 1 or limit > 50:
        raise ValidationError("Query parameter `limit` must be between 1 and 50.")
    entity = repo.find_entity_by_stock_code(stock_code)
    if entity is None or entity.stock_code is None:
        raise NotFoundError(f"Stock not found: {stock_code}", details={"stock_code": stock_code})

    records = repo.get_event_impact(entity.entity_id, limit=limit)
    items: list[EventImpactItem] = []
    for rec in records:
        # Direction is only allowed when upstream has tagged it (workflow / judgment / structured evidence).
        direction = rec.direction if (rec.workflow_run_id or rec.judgment_id) else None
        if workflow_run_id and rec.workflow_run_id != workflow_run_id:
            continue
        items.append(
            EventImpactItem(
                event_name=rec.event_name,
                impact_score=rec.impact_score,
                impact_level=rec.impact_level,  # type: ignore[arg-type]
                direction=direction,  # type: ignore[arg-type]
                evidence_ids=list(rec.evidence_ids),
                workflow_run_id=rec.workflow_run_id,
                judgment_id=rec.judgment_id,
            )
        )

    return EventImpactRankingView(
        stock_code=entity.stock_code,
        ticker=entity.ticker or "",
        ranker="report_event_impact_ranker_v1",
        items=items,
        updated_at=repo.now_iso(),
    )


# -- Benefits & risks ------------------------------------------------------


def build_benefits_risks_view(
    *,
    stock_code: str,
    workflow_run_id: str | None,
) -> BenefitsRisksView:
    entity = repo.find_entity_by_stock_code(stock_code)
    if entity is None or entity.stock_code is None:
        raise NotFoundError(f"Stock not found: {stock_code}", details={"stock_code": stock_code})

    judgment = None
    if workflow_run_id:
        judgment = repo.get_judgment_by_workflow(workflow_run_id)
        if judgment is None:
            raise NotFoundError(
                f"Workflow run not found: {workflow_run_id}",
                details={"workflow_run_id": workflow_run_id},
                code="WORKFLOW_NOT_FOUND",
            )
    else:
        judgment = repo.latest_judgment_for_entity(entity.entity_id)

    if judgment is None:
        # report_generation mode — benefits MUST be empty; risks only from evidence
        # tagged as risk_disclosure.
        risk_evidence = [
            e for e in repo.evidence_for_entity(entity.entity_id) if "risk_disclosure" in e.tags
        ]
        risks = [
            RiskItem(
                text=e.objective_summary,
                evidence_ids=[e.evidence_id],
                source="evidence_structure_risk_disclosure",
            )
            for e in risk_evidence
        ]
        return BenefitsRisksView(
            stock_code=entity.stock_code,
            ticker=entity.ticker or "",
            workflow_run_id=None,
            report_run_id=_new_report_run_id(entity.ticker or "0"),
            benefits=[],
            risks=risks,
            updated_at=repo.now_iso(),
        )

    return BenefitsRisksView(
        stock_code=entity.stock_code,
        ticker=entity.ticker or "",
        workflow_run_id=judgment.workflow_run_id,
        report_run_id=_new_report_run_id(entity.ticker or "0"),
        benefits=[BenefitItem(**item) for item in judgment.benefits],
        risks=[RiskItem(**item) for item in judgment.risks],
        updated_at=judgment.updated_at,
    )


# -- Market: index-overview ------------------------------------------------


def build_index_overview(*, refresh: RefreshPolicy) -> tuple[IndexOverview, str | None]:
    indices = []
    for snap in repo.list_index_snapshots():
        payload = snap.payload
        indices.append(
            IndexQuote(
                name=payload["name"],
                code=payload["code"],
                value=payload["value"],
                change_rate=payload["change_rate"],
                is_up=payload["is_up"],
                snapshot_id=snap.snapshot_id,
            )
        )

    sentiment_snap = repo.get_sentiment_snapshot()
    if sentiment_snap is None:
        sentiment = MarketSentiment(
            label="未知",
            score=0,
            source="market_snapshot_projection",
            snapshot_ids=[],
        )
    else:
        sentiment = MarketSentiment(
            label=sentiment_snap.payload["label"],
            score=sentiment_snap.payload["score"],
            source="market_snapshot_projection",
            snapshot_ids=[sentiment_snap.snapshot_id],
        )

    data_state = DataState.READY
    refresh_task_id: str | None = None
    if refresh == RefreshPolicy.STALE and not indices:
        data_state = DataState.PENDING_REFRESH
        refresh_task_id = _new_refresh_task_id()

    overview = IndexOverview(
        indices=indices,
        market_sentiment=sentiment,
        data_state=data_state,
        refresh_task_id=refresh_task_id,
        updated_at=repo.now_iso(),
    )
    return overview, refresh_task_id


# -- Market: stocks --------------------------------------------------------


def build_market_stocks(
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    refresh: RefreshPolicy,
) -> MarketStocksList:
    if page < 1:
        raise ValidationError("Query parameter `page` must be >= 1.")
    if page_size < 1 or page_size > 100:
        raise ValidationError("Query parameter `page_size` must be between 1 and 100.")

    rows = repo.list_stock_snapshots(keyword=keyword)
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    sliced = rows[start:end]

    data_rows: list[MarketStockRow] = []
    for entity, snap in sliced:
        payload = snap.payload
        if entity.stock_code is None:
            continue
        data_rows.append(
            MarketStockRow(
                stock_code=entity.stock_code,
                ticker=entity.ticker or "",
                name=entity.name,
                price=payload["price"],
                change_rate=payload["change_rate"],
                is_up=payload["is_up"],
                view_score=payload["view_score"],
                view_label=payload["view_label"],
                entity_id=entity.entity_id,
                snapshot_id=snap.snapshot_id,
            )
        )

    data_state = DataState.READY
    refresh_task_id: str | None = None
    if not data_rows and refresh in {RefreshPolicy.MISSING, RefreshPolicy.STALE}:
        data_state = DataState.PENDING_REFRESH
        refresh_task_id = _new_refresh_task_id()

    return MarketStocksList(
        list=data_rows,
        pagination=MarketStocksPagination(page=page, page_size=page_size, total=total),
        data_state=data_state,
        refresh_task_id=refresh_task_id,
    )


# -- Market: concept-radar --------------------------------------------------


def build_concept_radar(*, limit: int) -> tuple[list[ConceptRadarItem], DataState]:
    if limit < 1 or limit > 100:
        raise ValidationError("Query parameter `limit` must be between 1 and 100.")
    records = repo.list_concepts(limit=limit)
    items = [
        ConceptRadarItem(
            concept_name=r.concept_name,
            entity_id=r.entity_id,
            status=r.status,
            heat_score=r.heat_score,
            trend=r.trend,  # type: ignore[arg-type]
            snapshot_ids=list(r.snapshot_ids),
            evidence_ids=list(r.evidence_ids),
        )
        for r in records
    ]
    return items, DataState.READY


# -- Market: warnings ------------------------------------------------------


def build_market_warnings(
    *,
    limit: int,
    severity: str | None,
) -> tuple[list[MarketWarning], DataState]:
    if limit < 1 or limit > 100:
        raise ValidationError("Query parameter `limit` must be between 1 and 100.")
    if severity and severity not in {"info", "notice", "alert"}:
        raise ValidationError(
            "Query parameter `severity` must be one of info|notice|alert.",
            details={"severity": severity},
        )

    records = repo.list_warnings(limit=limit, severity=severity)
    items = [
        MarketWarning(
            warning_id=r.warning_id,
            time=r.time,
            title=r.title,
            content=r.content,
            severity=r.severity,  # type: ignore[arg-type]
            related_stock_codes=list(r.related_stock_codes),
            related_entity_ids=list(r.related_entity_ids),
            snapshot_ids=list(r.snapshot_ids),
            evidence_ids=list(r.evidence_ids),
        )
        for r in records
    ]
    return items, DataState.READY
