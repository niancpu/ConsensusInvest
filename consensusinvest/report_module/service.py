"""Report Module view assembler service.

The Report Module only projects already-owned runtime data. It must not carry
fixture facts or invent missing market, entity, or judgment state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from consensusinvest.agent_swarm.models import JudgmentRecord
from consensusinvest.agent_swarm.repository import InMemoryAgentSwarmRepository
from consensusinvest.common.errors import NotFoundError, ValidationError
from consensusinvest.entities.repository import EntityRecord, EntityRelationRecord, InMemoryEntityRepository
from consensusinvest.evidence_store.client import EvidenceStoreClient
from consensusinvest.evidence_store.models import (
    EvidenceDetail,
    EvidenceItem,
    EvidenceQuery,
    EvidenceReferenceBatch,
    MarketSnapshot,
    MarketSnapshotQuery,
)
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.runtime.wiring import AppRuntime
from consensusinvest.search_agent.models import (
    SearchBudget,
    SearchCallback,
    SearchConstraints,
    SearchExpansionPolicy,
    SearchScope,
    SearchTarget,
    SearchTask,
)

from .schemas import (
    ActionView,
    BenefitItem,
    BenefitsRisksView,
    ConceptRadarItem,
    DataState,
    EventImpactItem,
    EventImpactRankingView,
    EvidenceMatch,
    IndustryLinks,
    IndexOverview,
    IndexQuote,
    IndustryDetailsView,
    IndexIntradayPoint,
    IndexIntradayView,
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
from .repository import ReportRunRecord, ReportViewCacheRecord


@dataclass(slots=True)
class ReportRuntimeReader:
    evidence_store: EvidenceStoreClient
    entity_repository: InMemoryEntityRepository
    agent_repository: InMemoryAgentSwarmRepository
    workflow_repository: Any | None = None
    search_pool: Any | None = None
    report_repository: Any | None = None

    @classmethod
    def from_runtime(cls, runtime: AppRuntime, report_repository: Any | None = None) -> ReportRuntimeReader:
        return cls(
            evidence_store=runtime.evidence_store,
            entity_repository=runtime.entity_repository,
            agent_repository=runtime.agent_repository,
            workflow_repository=runtime.workflow_repository,
            search_pool=runtime.search_pool,
            report_repository=report_repository or getattr(runtime, "report_repository", None),
        )

    def search_entities(self, keyword: str, limit: int) -> list[EntityRecord]:
        rows, _ = self.entity_repository.list_entities(query=keyword, limit=limit, offset=0)
        return [row for row in rows if _stock_code(row) is not None]

    def find_entity_by_stock_code(self, stock_code: str) -> EntityRecord | None:
        needle = stock_code.strip().lower()
        rows, _ = self.entity_repository.list_entities(limit=1000, offset=0)
        for row in rows:
            values = {_stock_code(row), _ticker(row), *row.aliases}
            if any(value and value.lower() == needle for value in values):
                return row
        return None

    def evidence_for_entity(self, entity_id: str, *, limit: int = 20) -> list[EvidenceDetail]:
        page = self.evidence_store.query_evidence(
            _query_envelope(),
            EvidenceQuery(entity_ids=(entity_id,), limit=limit, offset=0),
        )
        return [_detail_or_item(self.evidence_store, item) for item in page.items]

    def evidence_for_keyword(self, keyword: str, *, limit: int) -> list[EvidenceDetail]:
        needle = keyword.strip().lower()
        if not needle:
            return []
        page = self.evidence_store.query_evidence(
            _query_envelope(),
            EvidenceQuery(limit=500, offset=0),
        )
        hits: list[EvidenceDetail] = []
        for item in page.items:
            haystacks = [item.title or "", item.content or "", item.evidence_type or ""]
            detail = _detail_or_item(self.evidence_store, item)
            if detail.structure is not None:
                haystacks.append(detail.structure.objective_summary)
            if any(needle in value.lower() for value in haystacks):
                hits.append(detail)
            if len(hits) >= limit:
                break
        return hits

    def judgment_by_workflow(self, workflow_run_id: str) -> JudgmentRecord | None:
        return self.agent_repository.get_judgment_by_workflow(workflow_run_id)

    def latest_judgment_for_entity(self, entity_id: str) -> JudgmentRecord | None:
        if self.workflow_repository is None:
            return None
        entity = _entity_by_id(self.entity_repository, entity_id)
        if entity is None:
            return None
        ticker = _ticker(entity)
        stock_code = _stock_code(entity)
        if ticker is None:
            return None

        offset = 0
        limit = 100
        while True:
            rows, total = self.workflow_repository.list_runs(ticker=ticker, limit=limit, offset=offset)
            for run in rows:
                if run.entity_id is not None and run.entity_id != entity_id:
                    continue
                if stock_code is not None and run.stock_code not in {None, stock_code}:
                    continue
                judgment = self.agent_repository.get_judgment_by_workflow(run.workflow_run_id)
                if judgment is not None:
                    return judgment
            offset += len(rows)
            if not rows or offset >= total:
                break
        return None

    def market_snapshots(self, snapshot_types: tuple[str, ...], *, limit: int = 50) -> list[MarketSnapshot]:
        page = self.evidence_store.query_market_snapshots(
            _query_envelope(),
            MarketSnapshotQuery(snapshot_types=snapshot_types, limit=limit, offset=0),
        )
        return page.items

    def market_snapshots_for_ticker(
        self,
        ticker: str,
        snapshot_types: tuple[str, ...],
        *,
        limit: int = 50,
    ) -> list[MarketSnapshot]:
        page = self.evidence_store.query_market_snapshots(
            _query_envelope(),
            MarketSnapshotQuery(ticker=ticker, snapshot_types=snapshot_types, limit=limit, offset=0),
        )
        return page.items


def _new_report_run_id(ticker: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"rpt_{today}_{ticker}_{uuid4().hex[:4]}"


def _report_run_id(reader: ReportRuntimeReader, ticker: str) -> str:
    if reader.report_repository is not None:
        return str(reader.report_repository.new_report_run_id(ticker or "0"))
    return _new_report_run_id(ticker or "0")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item not in seen:
            seen[item] = None
    return list(seen.keys())


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
    summary_text = (
        "报告视图基于已入库 Evidence Structure 与 MarketSnapshot 拼装，"
        "未运行主 workflow；不含 Agent Swarm 论证或 Judge 结论。"
    )
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

    key_evidence = [
        KeyEvidence(
            evidence_id=detail.evidence.evidence_id,
            title=detail.evidence.title or detail.evidence.evidence_id,
            objective_summary=_summary(detail),
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
    view = IndustryDetailsView(
        stock_code=_stock_code(entity) or stock_code,
        ticker=_ticker(entity) or "",
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
    return EventImpactRankingView(
        stock_code=_stock_code(entity) or stock_code,
        ticker=_ticker(entity) or "",
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


def build_index_overview(
    *,
    reader: ReportRuntimeReader,
    refresh: RefreshPolicy,
) -> tuple[IndexOverview, str | None]:
    indices = [
        IndexQuote(
            name=str(snapshot.metrics.get("name") or snapshot.ticker or snapshot.market_snapshot_id),
            code=str(snapshot.metrics.get("code") or snapshot.ticker or snapshot.market_snapshot_id),
            value=float(snapshot.metrics.get("value") or 0),
            change_rate=float(snapshot.metrics.get("change_rate") or 0),
            is_up=bool(snapshot.metrics.get("is_up") or False),
            snapshot_id=snapshot.market_snapshot_id,
        )
        for snapshot in reader.market_snapshots(("index_quote",), limit=20)
    ]
    data_state = DataState.READY if indices else DataState.MISSING
    refresh_task_id = None
    report_run_id = _report_run_id(reader, "MARKET")
    if not indices and refresh in {RefreshPolicy.MISSING, RefreshPolicy.STALE}:
        data_state = DataState.PENDING_REFRESH
        refresh_task_id = _request_market_refresh(
            reader=reader,
            market_view="index_overview",
            reason="missing",
            report_run_id=report_run_id,
            metadata={},
        )

    overview = IndexOverview(
        indices=indices,
        market_sentiment=MarketSentiment(
            label="未知",
            score=0,
            source="market_snapshot_projection",
            snapshot_ids=[],
        ),
        data_state=data_state,
        refresh_task_id=refresh_task_id,
        updated_at=_now_iso(),
    )
    snapshot_ids = _dedupe(
        [
            *(quote.snapshot_id for quote in overview.indices),
            *overview.market_sentiment.snapshot_ids,
        ]
    )
    _save_report_run(
        reader=reader,
        report_run_id=report_run_id,
        ticker="MARKET",
        stock_code=None,
        report_mode=ReportMode.REPORT_GENERATION,
        data_state=overview.data_state,
        workflow_run_id=None,
        judgment_id=None,
        entity_id=None,
        input_refs=_input_refs(
            evidence_ids=[],
            market_snapshot_ids=snapshot_ids,
            workflow_run_id=None,
            judgment_id=None,
        ),
        output_snapshot=_jsonable(overview),
        limitations=_market_limitations(),
        refresh_task_id=refresh_task_id,
    )
    return overview, refresh_task_id


def build_index_intraday(
    *,
    reader: ReportRuntimeReader,
    code: str,
    refresh: RefreshPolicy,
) -> tuple[IndexIntradayView, str | None]:
    normalized_code = _normalize_index_code(code)
    ticker = _index_ticker(normalized_code)
    matching = _index_intraday_snapshots(reader, normalized_code, ticker)
    points = _intraday_points_from_snapshots(matching)
    data_state = DataState.READY if points else DataState.MISSING
    refresh_task_id = None
    report_run_id = _report_run_id(reader, f"INDEX_INTRADAY_{ticker}")
    if not points and refresh in {RefreshPolicy.MISSING, RefreshPolicy.STALE}:
        data_state = DataState.PENDING_REFRESH
        refresh_task_id = _request_market_refresh(
            reader=reader,
            market_view="index_intraday",
            reason="missing",
            report_run_id=report_run_id,
            metadata={"code": normalized_code, "ticker": ticker},
        )
        if (
            refresh_task_id
            and _market_refresh_can_run_now(reader.search_pool, market_view="index_intraday")
            and _run_refresh_task_once(reader, refresh_task_id)
        ):
            matching = _index_intraday_snapshots(reader, normalized_code, ticker)
            points = _intraday_points_from_snapshots(matching)
            if points:
                data_state = DataState.READY
            elif _search_task_status(reader, refresh_task_id) in {"failed", "cancelled"}:
                data_state = DataState.FAILED
            else:
                data_state = DataState.MISSING
        elif refresh_task_id and _search_task_status(reader, refresh_task_id) in {"failed", "cancelled"}:
            data_state = DataState.FAILED

    latest = matching[0] if matching else None
    view = IndexIntradayView(
        code=normalized_code,
        name=str(latest.metrics.get("name") or _index_name(normalized_code)) if latest else _index_name(normalized_code),
        trade_date=_trade_date(points, latest),
        points=points,
        previous_close=_float_or_none(latest.metrics.get("previous_close")) if latest else None,
        open=_float_or_none(latest.metrics.get("open")) if latest else None,
        high=_float_or_none(latest.metrics.get("high")) if latest else None,
        low=_float_or_none(latest.metrics.get("low")) if latest else None,
        snapshot_ids=_dedupe(snapshot.market_snapshot_id for snapshot in matching),
        data_state=data_state,
        refresh_task_id=refresh_task_id,
        updated_at=_dt(latest.snapshot_time) if latest else _now_iso(),
    )
    output_snapshot = _jsonable(view)
    if refresh_task_id is not None:
        output_snapshot["refresh_task_id"] = refresh_task_id
    _save_report_run(
        reader=reader,
        report_run_id=report_run_id,
        ticker=f"INDEX_INTRADAY_{ticker}",
        stock_code=None,
        report_mode=ReportMode.REPORT_GENERATION,
        data_state=view.data_state,
        workflow_run_id=None,
        judgment_id=None,
        entity_id=None,
        input_refs=_input_refs(
            evidence_ids=[],
            market_snapshot_ids=view.snapshot_ids,
            workflow_run_id=None,
            judgment_id=None,
        ),
        output_snapshot=output_snapshot,
        limitations=_market_limitations(),
        refresh_task_id=refresh_task_id,
    )
    return view, refresh_task_id


def build_market_stocks(
    *,
    reader: ReportRuntimeReader,
    page: int,
    page_size: int,
    keyword: str | None,
    refresh: RefreshPolicy,
) -> MarketStocksList:
    if page < 1:
        raise ValidationError("Query parameter `page` must be >= 1.")
    if page_size < 1 or page_size > 100:
        raise ValidationError("Query parameter `page_size` must be between 1 and 100.")

    rows = [
        snapshot
        for snapshot in reader.market_snapshots(("stock_quote",), limit=1000)
        if _snapshot_matches_keyword(snapshot, keyword)
    ]
    total = len(rows)
    sliced = rows[(page - 1) * page_size : page * page_size]
    data_rows = [
        MarketStockRow(
            stock_code=str(snapshot.metrics.get("stock_code") or snapshot.ticker or ""),
            ticker=str(snapshot.ticker or snapshot.metrics.get("ticker") or ""),
            name=str(snapshot.metrics.get("name") or snapshot.ticker or ""),
            price=float(snapshot.metrics.get("price") or 0),
            change_rate=float(snapshot.metrics.get("change_rate") or 0),
            is_up=bool(snapshot.metrics.get("is_up") or False),
            view_score=int(snapshot.metrics.get("view_score") or 0),
            view_label=str(snapshot.metrics.get("view_label") or "未评级"),
            entity_id=next(iter(snapshot.entity_ids), ""),
            snapshot_id=snapshot.market_snapshot_id,
        )
        for snapshot in sliced
    ]
    data_state = DataState.READY if data_rows else DataState.MISSING
    refresh_task_id = None
    report_run_id = _report_run_id(reader, "MARKET_STOCKS")
    if not data_rows and refresh in {RefreshPolicy.MISSING, RefreshPolicy.STALE}:
        data_state = DataState.PENDING_REFRESH
        refresh_task_id = _request_market_refresh(
            reader=reader,
            market_view="market_stocks",
            reason="missing",
            report_run_id=report_run_id,
            metadata={"page": page, "page_size": page_size, "keyword": keyword},
        )
    payload = MarketStocksList(
        list=data_rows,
        pagination=MarketStocksPagination(page=page, page_size=page_size, total=total),
        data_state=data_state,
        refresh_task_id=refresh_task_id,
    )
    _save_report_run(
        reader=reader,
        report_run_id=report_run_id,
        ticker="MARKET_STOCKS",
        stock_code=None,
        report_mode=ReportMode.REPORT_GENERATION,
        data_state=payload.data_state,
        workflow_run_id=None,
        judgment_id=None,
        entity_id=None,
        input_refs=_input_refs(
            evidence_ids=[],
            market_snapshot_ids=_dedupe(row.snapshot_id for row in payload.list),
            workflow_run_id=None,
            judgment_id=None,
        ),
        output_snapshot=_jsonable(payload),
        limitations=_market_limitations(),
        refresh_task_id=refresh_task_id,
    )
    return payload


def build_concept_radar(*, reader: ReportRuntimeReader, limit: int) -> tuple[list[ConceptRadarItem], DataState]:
    if limit < 1 or limit > 100:
        raise ValidationError("Query parameter `limit` must be between 1 and 100.")
    snapshots = reader.market_snapshots(("concept_heat",), limit=limit)
    items = [
        ConceptRadarItem(
            concept_name=str(snapshot.metrics.get("concept_name") or snapshot.ticker or snapshot.market_snapshot_id),
            entity_id=next(iter(snapshot.entity_ids), ""),
            status=str(snapshot.metrics.get("status") or "未知"),
            heat_score=int(snapshot.metrics.get("heat_score") or 0),
            trend=_trend(snapshot.metrics.get("trend")),
            snapshot_ids=[snapshot.market_snapshot_id],
            evidence_ids=_string_list(snapshot.metrics.get("evidence_ids")),
        )
        for snapshot in snapshots
    ]
    data_state = DataState.READY if items else DataState.MISSING
    _save_market_list_run(
        reader=reader,
        ticker="MARKET_CONCEPT_RADAR",
        items=items,
        data_state=data_state,
    )
    return items, data_state


def build_market_warnings(
    *,
    reader: ReportRuntimeReader,
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

    snapshots = reader.market_snapshots(("market_warning",), limit=limit)
    items: list[MarketWarning] = []
    for snapshot in snapshots:
        item_severity = str(snapshot.metrics.get("severity") or "info")
        if item_severity not in {"info", "notice", "alert"}:
            item_severity = "info"
        if severity and item_severity != severity:
            continue
        items.append(
            MarketWarning(
                warning_id=str(snapshot.metrics.get("warning_id") or snapshot.market_snapshot_id),
                time=str(snapshot.metrics.get("time") or _dt(snapshot.snapshot_time)),
                title=str(snapshot.metrics.get("title") or "市场预警"),
                content=str(snapshot.metrics.get("content") or ""),
                severity=item_severity,  # type: ignore[arg-type]
                related_stock_codes=_string_list(snapshot.metrics.get("related_stock_codes")),
                related_entity_ids=list(snapshot.entity_ids),
                snapshot_ids=[snapshot.market_snapshot_id],
                evidence_ids=_string_list(snapshot.metrics.get("evidence_ids")),
            )
        )
    data_state = DataState.READY if items else DataState.MISSING
    _save_market_list_run(
        reader=reader,
        ticker="MARKET_WARNINGS",
        items=items,
        data_state=data_state,
    )
    return items, data_state


def _selected_judgment(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    *,
    workflow_run_id: str | None,
    latest: bool,
) -> JudgmentRecord | None:
    if workflow_run_id:
        judgment = reader.judgment_by_workflow(workflow_run_id)
        if judgment is None:
            raise NotFoundError(
                f"Workflow run not found: {workflow_run_id}",
                code="WORKFLOW_NOT_FOUND",
                details={"workflow_run_id": workflow_run_id},
            )
        return judgment
    if latest:
        return reader.latest_judgment_for_entity(entity.entity_id)
    return None


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


def _jsonable(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return dict(asdict(value))
    return dict(value)


def _stock_limitations(report_mode: ReportMode) -> list[str]:
    if report_mode == ReportMode.WITH_WORKFLOW_TRACE:
        return ["本报告视图仅投影已入库主 workflow、Judgment 与 Evidence 引用，不生成新的投资判断。"]
    return ["本报告未运行主 workflow，因此没有 Agent Swarm 论证链和 Judge 最终判断。"]


def _market_limitations() -> list[str]:
    return ["市场视图仅投影已入库 MarketSnapshot 和引用信息，不构成投资建议。"]


def _required_stock(reader: ReportRuntimeReader, stock_code: str) -> EntityRecord:
    entity = reader.find_entity_by_stock_code(stock_code)
    if entity is None or _stock_code(entity) is None:
        raise NotFoundError(f"Stock not found: {stock_code}", details={"stock_code": stock_code})
    return entity


def _industry_relation(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
) -> tuple[EntityRelationRecord | None, EntityRecord | None]:
    relation_types = {"belongs_to_industry", "industry", "in_industry", "has_company"}
    for relation in reader.entity_repository.list_relations(entity.entity_id, depth=1):
        if relation.relation_type not in relation_types:
            continue
        other_id = relation.to_entity_id if relation.from_entity_id == entity.entity_id else relation.from_entity_id
        other = _entity_by_id(reader.entity_repository, other_id)
        if other is not None and other.entity_type == "industry":
            return relation, other
    return None, None


def _industry_evidence(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    relation: EntityRelationRecord,
    industry: EntityRecord,
    *,
    workflow_run_id: str | None,
) -> list[EvidenceDetail]:
    details_by_id: dict[str, EvidenceDetail] = {}
    for evidence_id in relation.evidence_ids:
        detail = _detail_by_id(reader.evidence_store, evidence_id)
        if detail is not None:
            details_by_id[detail.evidence.evidence_id] = detail
    for detail in [
        *reader.evidence_for_entity(industry.entity_id, limit=20),
        *reader.evidence_for_entity(entity.entity_id, limit=20),
    ]:
        item = detail.evidence
        if workflow_run_id is not None and not _detail_matches_workflow(detail, workflow_run_id):
            continue
        if item.evidence_type in {"industry_news", "policy", "company_news", "financial_report", "risk_disclosure"}:
            details_by_id[item.evidence_id] = detail
    return sorted(details_by_id.values(), key=_detail_sort_key, reverse=True)


def _event_evidence(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    *,
    workflow_run_id: str | None,
    limit: int,
) -> list[EvidenceDetail]:
    event_types = (
        "company_news",
        "industry_news",
        "announcement",
        "financial_report",
        "policy",
        "macro_event",
        "market_event",
    )
    page = reader.evidence_store.query_evidence(
        _query_envelope(),
        EvidenceQuery(
            ticker=_ticker(entity),
            entity_ids=(entity.entity_id,),
            workflow_run_id=workflow_run_id,
            evidence_types=event_types,
            limit=limit * 4,
            offset=0,
        ),
    )
    details = [_detail_or_item(reader.evidence_store, item) for item in page.items]
    details.sort(key=lambda detail: (_event_score(detail), *_detail_sort_key(detail)), reverse=True)
    return details[:limit]


def _detail_by_id(evidence_store: EvidenceStoreClient, evidence_id: str) -> EvidenceDetail | None:
    try:
        return evidence_store.get_evidence(_query_envelope(), evidence_id)
    except KeyError:
        return None


def _detail_matches_workflow(detail: EvidenceDetail, workflow_run_id: str) -> bool:
    return any(ref.workflow_run_id == workflow_run_id for ref in detail.references)


def _detail_sort_key(detail: EvidenceDetail) -> tuple[datetime, str]:
    return (_comparable_dt(detail.evidence.publish_time), detail.evidence.evidence_id)


def _industry_text(
    records: list[EvidenceDetail],
    *,
    fact_names: tuple[str, ...],
    keywords: tuple[str, ...],
    fallback: str,
) -> str:
    fact = _first_fact_text(records, fact_names)
    if fact is not None:
        return fact
    keyword_text = _first_keyword_summary(records, keywords)
    if keyword_text is not None:
        return keyword_text
    return fallback


def _first_fact_text(records: list[EvidenceDetail], names: tuple[str, ...]) -> str | None:
    normalized_names = {name.lower() for name in names}
    for detail in records:
        structure = detail.structure
        if structure is None:
            continue
        for fact in structure.key_facts:
            name = str(fact.get("name") or "").strip().lower()
            if name not in normalized_names:
                continue
            value = str(fact.get("value") or "").strip()
            unit = str(fact.get("unit") or "").strip()
            if value:
                return f"{value}{unit}"
    return None


def _first_keyword_summary(records: list[EvidenceDetail], keywords: tuple[str, ...]) -> str | None:
    for detail in records:
        text = _summary(detail).strip()
        if text and any(keyword in text for keyword in keywords):
            return text
    return None


def _policy_support_level(records: list[EvidenceDetail]) -> str:
    fact = _first_fact_text(records, ("policy_support_level", "政策支持等级"))
    if fact in {"low", "medium", "high"}:
        return fact
    if _first_keyword_summary(records, ("大力支持", "强支持", "重点支持", "政策支持力度较强")) is not None:
        return "high"
    if _first_keyword_summary(records, ("政策", "支持", "补贴", "规划")) is not None:
        return "medium"
    return "low"


def _event_name(detail: EvidenceDetail) -> str:
    structure = detail.structure
    if structure is not None:
        for fact in structure.key_facts:
            name = str(fact.get("name") or "").strip().lower()
            if name in {"event_name", "event", "事件"}:
                value = str(fact.get("value") or "").strip()
                if value:
                    return value
    item = detail.evidence
    return item.title or _summary(detail)[:80] or item.evidence_id


def _event_score(detail: EvidenceDetail) -> int:
    item = detail.evidence
    quality = item.source_quality if item.source_quality is not None else 0.5
    relevance = item.relevance if item.relevance is not None else 0.5
    freshness = item.freshness if item.freshness is not None else 0.5
    score = int(round((quality * 0.4 + relevance * 0.4 + freshness * 0.2) * 100))
    return max(0, min(score, 100))


def _event_level(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _entity_by_id(repository: Any, entity_id: str) -> EntityRecord | None:
    getter = getattr(repository, "get_entity", None)
    if callable(getter):
        return getter(entity_id)
    rows, _ = repository.list_entities(limit=1000, offset=0)
    for row in rows:
        if row.entity_id == entity_id:
            return row
    return None


def _request_stock_refresh(
    *,
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    ticker: str,
    stock_code: str,
    query: str | None,
    report_run_id: str,
) -> str | None:
    if reader.search_pool is None:
        return None

    analysis_time = datetime.now(timezone.utc)
    idempotency_key = _report_refresh_idempotency_key(ticker=ticker, analysis_time=analysis_time, reason="missing")
    envelope = InternalCallEnvelope(
        request_id=f"req_report_refresh_{uuid4().hex[:8]}",
        correlation_id=f"corr_report_refresh_{uuid4().hex[:8]}",
        workflow_run_id=None,
        analysis_time=analysis_time,
        requested_by="report_module",
        idempotency_key=idempotency_key,
        trace_level="standard",
    )
    receipt = reader.search_pool.submit(
        envelope,
        SearchTask(
            task_type="stock_research",
            target=SearchTarget(
                query=query,
                ticker=ticker,
                stock_code=stock_code,
                entity_id=entity.entity_id,
                keywords=_stock_refresh_keywords(entity, query=query),
                metadata={"report_run_id": report_run_id},
            ),
            scope=SearchScope(
                sources=_stock_refresh_sources(reader.search_pool),
                evidence_types=("company_news", "financial_report", "industry_news"),
                lookback_days=30,
                max_results=30,
            ),
            constraints=SearchConstraints(
                allow_stale_cache=True,
                dedupe_hint=True,
                language="zh-CN",
                expansion_policy=SearchExpansionPolicy(
                    allowed=True,
                    max_depth=1,
                    allowed_actions=(
                        "fetch_original_url",
                        "follow_official_source",
                        "provider_pagination",
                        "same_event_cross_source",
                    ),
                ),
                budget=SearchBudget(max_provider_calls=20, max_runtime_ms=60000),
            ),
            idempotency_key=idempotency_key,
            callback=SearchCallback(
                ingest_target="evidence_store",
                workflow_run_id=None,
                metadata={"reason": "missing_stock_analysis", "report_run_id": report_run_id},
            ),
            metadata={"reason": "missing_stock_analysis", "report_run_id": report_run_id},
        ),
    )
    return _task_id(receipt)


def _request_market_refresh(
    *,
    reader: ReportRuntimeReader,
    market_view: str,
    reason: str,
    report_run_id: str,
    metadata: dict[str, Any],
) -> str | None:
    if reader.search_pool is None:
        return None

    analysis_time = datetime.now(timezone.utc)
    idempotency_key = _market_refresh_idempotency_key(
        market_view=market_view,
        analysis_time=analysis_time,
        reason=reason,
    )
    envelope = InternalCallEnvelope(
        request_id=f"req_report_market_refresh_{uuid4().hex[:8]}",
        correlation_id=f"corr_report_market_refresh_{uuid4().hex[:8]}",
        workflow_run_id=None,
        analysis_time=analysis_time,
        requested_by="report_module",
        idempotency_key=idempotency_key,
        trace_level="standard",
    )
    task_metadata = {
        "reason": f"{reason}_{market_view}",
        "report_run_id": report_run_id,
        "market_view": market_view,
        **metadata,
    }
    receipt = reader.search_pool.submit(
        envelope,
        SearchTask(
            task_type="market_snapshot",
            target=SearchTarget(
                query=_market_refresh_query(market_view),
                entity_type="market",
                keywords=_market_refresh_keywords(market_view, metadata=metadata),
                metadata=task_metadata,
            ),
            scope=SearchScope(
                sources=_market_refresh_sources(reader.search_pool, market_view=market_view),
                evidence_types=_market_refresh_evidence_types(market_view),
                lookback_days=3,
                max_results=50,
                locale="zh-CN",
                metadata={"market_view": market_view},
            ),
            constraints=SearchConstraints(
                allow_stale_cache=True,
                dedupe_hint=True,
                language="zh-CN",
                expansion_policy=SearchExpansionPolicy(
                    allowed=False,
                    max_depth=0,
                    allowed_actions=(),
                ),
                budget=SearchBudget(max_provider_calls=10, max_runtime_ms=30000),
            ),
            idempotency_key=idempotency_key,
            callback=SearchCallback(
                ingest_target="evidence_store",
                workflow_run_id=None,
                metadata=task_metadata,
            ),
            metadata=task_metadata,
        ),
    )
    return _task_id(receipt)


def _report_refresh_idempotency_key(*, ticker: str, analysis_time: datetime, reason: str) -> str:
    return f"report_refresh_{ticker}_{analysis_time.strftime('%Y%m%d')}_{reason}"


def _market_refresh_idempotency_key(*, market_view: str, analysis_time: datetime, reason: str) -> str:
    return f"report_market_refresh_{analysis_time.strftime('%Y%m%d')}_{market_view}_{reason}"


def _market_refresh_query(market_view: str) -> str:
    if market_view == "index_overview":
        return "A股主要指数行情与市场情绪快照"
    if market_view == "index_intraday":
        return "A股主要指数日内走势快照"
    if market_view == "market_stocks":
        return "A股市场股票行情列表快照"
    return "A股市场行情快照"


def _market_refresh_keywords(market_view: str, *, metadata: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = ["A股", "市场行情"]
    if market_view == "index_overview":
        values.extend(["上证指数", "深证成指", "创业板指", "市场情绪"])
    elif market_view == "index_intraday":
        values.extend(["上证指数", "指数分时", "日内走势"])
        code = metadata.get("code")
        ticker = metadata.get("ticker")
        if code:
            values.append(str(code))
        if ticker:
            values.append(str(ticker))
    elif market_view == "market_stocks":
        values.extend(["股票行情", "涨跌幅", "市场股票列表"])
        keyword = metadata.get("keyword")
        if keyword:
            values.append(str(keyword))
    return tuple(_dedupe(value for value in values if value))


def _market_refresh_evidence_types(market_view: str) -> tuple[str, ...]:
    if market_view == "index_overview":
        return ("index_quote", "market_sentiment", "market_snapshot")
    if market_view == "index_intraday":
        return ("index_quote", "market_snapshot")
    if market_view == "market_stocks":
        return ("stock_quote", "market_snapshot")
    return ("market_snapshot",)


def _stock_refresh_keywords(entity: EntityRecord, *, query: str | None) -> tuple[str, ...]:
    values = [entity.name, _ticker(entity) or "", _stock_code(entity) or "", *entity.aliases]
    if query:
        values.append(query)
    keywords: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in keywords:
            keywords.append(text)
    return tuple(keywords)


def _stock_refresh_sources(search_pool: Any) -> tuple[str, ...]:
    providers = getattr(search_pool, "providers", None)
    if isinstance(providers, dict) and providers:
        return tuple(str(source) for source in providers.keys())
    provider = getattr(search_pool, "provider", None)
    source = getattr(provider, "source", None)
    if source:
        return (str(source),)
    return ("tavily", "exa")


def _market_refresh_sources(search_pool: Any, *, market_view: str) -> tuple[str, ...]:
    providers = getattr(search_pool, "providers", None)
    if market_view in {"index_overview", "index_intraday", "market_stocks"}:
        if isinstance(providers, dict) and "akshare" in providers:
            return ("akshare",)
        provider = getattr(search_pool, "provider", None)
        source = getattr(provider, "source", None)
        if source == "akshare":
            return ("akshare",)
        return ("akshare",)
    return _stock_refresh_sources(search_pool)


def _market_refresh_can_run_now(search_pool: Any, *, market_view: str) -> bool:
    if search_pool is None or market_view not in {"index_overview", "index_intraday", "market_stocks"}:
        return False
    providers = getattr(search_pool, "providers", None)
    if isinstance(providers, dict):
        return "akshare" in providers
    provider = getattr(search_pool, "provider", None)
    return getattr(provider, "source", None) == "akshare"


def _run_refresh_task_once(reader: ReportRuntimeReader, refresh_task_id: str) -> bool:
    search_pool = reader.search_pool
    if search_pool is None:
        return False
    run_task_once = getattr(search_pool, "run_task_once", None)
    if callable(run_task_once):
        return bool(run_task_once(refresh_task_id))
    run_pending_once = getattr(search_pool, "run_pending_once", None)
    if callable(run_pending_once):
        return refresh_task_id in set(str(task_id) for task_id in run_pending_once())
    return False


def _search_task_status(reader: ReportRuntimeReader, refresh_task_id: str) -> str | None:
    search_pool = reader.search_pool
    repository = getattr(search_pool, "repository", None)
    get_task_status = getattr(repository, "get_task_status", None)
    if not callable(get_task_status):
        return None
    status = get_task_status(refresh_task_id)
    if isinstance(status, dict):
        status = status.get("status")
    value = getattr(status, "value", status)
    return str(value) if value else None


def _task_id(receipt: Any) -> str | None:
    if isinstance(receipt, dict):
        value = receipt.get("task_id")
    else:
        value = getattr(receipt, "task_id", None)
    return str(value) if value else None


def _detail_or_item(evidence_store: EvidenceStoreClient, item: EvidenceItem) -> EvidenceDetail:
    try:
        return evidence_store.get_evidence(_query_envelope(), item.evidence_id)
    except KeyError:
        return EvidenceDetail(evidence=item, structure=None, raw_ref=item.raw_ref, references=[])


def _risk_disclosures(records: list[EvidenceDetail]) -> list[RiskItem]:
    risks: list[RiskItem] = []
    for detail in records:
        item = detail.evidence
        if item.evidence_type != "risk_disclosure":
            continue
        risks.append(
            RiskItem(
                text=_summary(detail),
                evidence_ids=[item.evidence_id],
                source="evidence_structure_risk_disclosure",
            )
        )
    return risks


def _summary(detail: EvidenceDetail) -> str:
    if detail.structure is not None:
        return detail.structure.objective_summary
    item = detail.evidence
    return item.content or item.title or item.evidence_id


def _stock_code(entity: EntityRecord) -> str | None:
    for value in entity.aliases:
        text = value.strip().upper()
        if "." in text and text.split(".", 1)[0].isdigit():
            return text
    return None


def _ticker(entity: EntityRecord) -> str | None:
    stock_code = _stock_code(entity)
    if stock_code:
        return stock_code.split(".", 1)[0]
    for value in entity.aliases:
        text = value.strip()
        if text.isdigit():
            return text
    return None


def _exchange(stock_code: str | None) -> str:
    if not stock_code or "." not in stock_code:
        return ""
    return stock_code.rsplit(".", 1)[1]


def _action_label(signal: str) -> str:
    return {"positive": "看多", "neutral": "观望", "negative": "看空"}.get(signal, signal)


def _snapshot_matches_keyword(snapshot: MarketSnapshot, keyword: str | None) -> bool:
    if not keyword or not keyword.strip():
        return True
    needle = keyword.strip().lower()
    values = [
        snapshot.ticker or "",
        str(snapshot.metrics.get("stock_code") or ""),
        str(snapshot.metrics.get("ticker") or ""),
        str(snapshot.metrics.get("name") or ""),
    ]
    return any(needle in value.lower() for value in values)


def _normalize_index_code(code: str) -> str:
    text = code.strip().upper()
    if text in {"000001", "SH000001"}:
        return "000001.SH"
    if text in {"399001", "SZ399001"}:
        return "399001.SZ"
    if text in {"399006", "SZ399006"}:
        return "399006.SZ"
    if "." in text:
        left, right = text.split(".", 1)
        return f"{left}.{right}"
    suffix = "SH" if text.startswith(("0", "5", "6", "9")) else "SZ"
    return f"{text}.{suffix}"


def _index_ticker(code: str) -> str:
    return code.split(".", 1)[0]


def _index_name(code: str) -> str:
    return {
        "000001.SH": "上证指数",
        "399001.SZ": "深证成指",
        "399006.SZ": "创业板指",
    }.get(code, code)


def _index_intraday_snapshots(
    reader: ReportRuntimeReader,
    normalized_code: str,
    ticker: str,
) -> list[MarketSnapshot]:
    snapshots = reader.market_snapshots_for_ticker(ticker, ("index_quote",), limit=500)
    return [
        snapshot
        for snapshot in snapshots
        if _normalize_index_code(str(snapshot.metrics.get("code") or snapshot.ticker or "")) == normalized_code
    ]


def _intraday_points_from_snapshots(snapshots: list[MarketSnapshot]) -> list[IndexIntradayPoint]:
    if not snapshots:
        return []
    latest = snapshots[0]
    raw_points = latest.metrics.get("intraday_points")
    if isinstance(raw_points, list) and raw_points:
        points = [_intraday_point_from_mapping(item, latest) for item in raw_points if isinstance(item, dict)]
        return [point for point in points if point is not None]

    points: list[IndexIntradayPoint] = []
    for snapshot in reversed(snapshots):
        value = _float_or_none(snapshot.metrics.get("value") or snapshot.metrics.get("close") or snapshot.metrics.get("price"))
        if value is None:
            continue
        timestamp = _dt(snapshot.snapshot_time)
        points.append(
            IndexIntradayPoint(
                time=_point_time(timestamp),
                timestamp=timestamp,
                value=value,
                change=_float_or_none(snapshot.metrics.get("change")),
                change_rate=_float_or_none(snapshot.metrics.get("change_rate")),
                volume=_float_or_none(snapshot.metrics.get("volume")),
                amount=_float_or_none(snapshot.metrics.get("amount")),
            )
        )
    return points


def _intraday_point_from_mapping(item: dict[str, Any], snapshot: MarketSnapshot) -> IndexIntradayPoint | None:
    value = _float_or_none(item.get("value") or item.get("close") or item.get("price"))
    if value is None:
        return None
    timestamp = str(item.get("timestamp") or item.get("datetime") or item.get("time") or _dt(snapshot.snapshot_time))
    return IndexIntradayPoint(
        time=str(item.get("time") or _point_time(timestamp)),
        timestamp=timestamp,
        value=value,
        change=_float_or_none(item.get("change")),
        change_rate=_float_or_none(item.get("change_rate")),
        volume=_float_or_none(item.get("volume")),
        amount=_float_or_none(item.get("amount")),
    )


def _point_time(timestamp: str) -> str:
    if "T" in timestamp:
        return timestamp.split("T", 1)[1][:5]
    if " " in timestamp:
        return timestamp.split(" ", 1)[1][:5]
    return timestamp[:5]


def _trade_date(points: list[IndexIntradayPoint], snapshot: MarketSnapshot | None) -> str:
    if points:
        timestamp = points[-1].timestamp
        if "T" in timestamp:
            return timestamp.split("T", 1)[0]
        if " " in timestamp:
            return timestamp.split(" ", 1)[0]
    if snapshot and snapshot.snapshot_time is not None:
        return snapshot.snapshot_time.date().isoformat()
    return ""


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trend(value: object) -> str:
    text = str(value or "flat")
    return text if text in {"warming", "cooling", "flat"} else "flat"


def _string_list(value: object) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []


def _query_envelope() -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="req_report_api_query",
        correlation_id="corr_report_api_query",
        workflow_run_id=None,
        analysis_time=datetime.now(timezone.utc),
        requested_by="report_module",
    )


def _dt(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _comparable_dt(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
