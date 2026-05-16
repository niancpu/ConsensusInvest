"""Market-oriented Report Module view builders."""

from __future__ import annotations

from consensusinvest.common.errors import ValidationError

from .runtime_reader import ReportRuntimeReader
from ._utils import _dedupe, _dt, _jsonable, _now_iso
from .projections import (
    _float_or_none,
    _index_intraday_snapshots,
    _index_name,
    _index_ticker,
    _intraday_points_from_snapshots,
    _normalize_index_code,
    _snapshot_matches_keyword,
    _string_list,
    _trade_date,
    _trend,
)
from .refresh import (
    _market_refresh_can_run_now,
    _request_market_refresh,
    _run_refresh_task_once,
    _search_task_status,
)
from .report_runs import (
    _input_refs,
    _market_limitations,
    _report_run_id,
    _save_market_list_run,
    _save_report_run,
)
from .schemas import (
    ConceptRadarItem,
    DataState,
    IndexIntradayView,
    IndexOverview,
    IndexQuote,
    MarketSentiment,
    MarketStockRow,
    MarketStocksList,
    MarketStocksPagination,
    MarketWarning,
    RefreshPolicy,
    ReportMode,
)



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
