"""FastAPI routes for the Report Module HTTP API.

Endpoints (per `docs/report_module/`):

- GET /api/v1/stocks/search
- GET /api/v1/stocks/{stock_code}/analysis
- GET /api/v1/stocks/{stock_code}/industry-details
- GET /api/v1/stocks/{stock_code}/event-impact-ranking
- GET /api/v1/stocks/{stock_code}/benefits-risks
- GET /api/v1/market/index-overview
- GET /api/v1/market/stocks
- GET /api/v1/market/concept-radar
- GET /api/v1/market/warnings
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..common.response import ListPagination, ListResponse, Meta, SingleResponse
from . import service
from .schemas import (
    BenefitsRisksView,
    ConceptRadarItem,
    EventImpactRankingView,
    IndexOverview,
    IndustryDetailsView,
    MarketStocksList,
    MarketWarning,
    RefreshPolicy,
    StockAnalysisView,
    StockSearchHit,
)

router = APIRouter(prefix="/api/v1", tags=["report_module"])


# -- Stocks ----------------------------------------------------------------


@router.get("/stocks/search", response_model=ListResponse[StockSearchHit])
def search_stocks(
    keyword: str = Query(..., description="股票代码、简称、公司名、别名或自然语言关键词。"),
    limit: int = Query(10, ge=1, le=50),
    include_evidence: bool = Query(True),
) -> ListResponse[StockSearchHit]:
    hits, data_state = service.build_stock_search(
        keyword=keyword, limit=limit, include_evidence=include_evidence
    )
    return ListResponse[StockSearchHit](
        data=hits,
        pagination=ListPagination(limit=limit, offset=0, total=len(hits), has_more=False),
        meta=Meta(data_state=data_state.value),
    )


@router.get("/stocks/{stock_code}/analysis", response_model=SingleResponse[StockAnalysisView])
def get_stock_analysis(
    stock_code: str,
    query: str | None = Query(None),
    workflow_run_id: str | None = Query(None),
    latest: bool = Query(True),
    refresh: RefreshPolicy = Query(RefreshPolicy.NEVER),
) -> SingleResponse[StockAnalysisView]:
    view = service.build_stock_analysis_view(
        stock_code=stock_code,
        query=query,
        workflow_run_id=workflow_run_id,
        latest=latest,
        refresh=refresh,
    )
    return SingleResponse[StockAnalysisView](data=view)


@router.get(
    "/stocks/{stock_code}/industry-details",
    response_model=SingleResponse[IndustryDetailsView],
)
def get_industry_details(
    stock_code: str,
    workflow_run_id: str | None = Query(None),
) -> SingleResponse[IndustryDetailsView]:
    view = service.build_industry_details_view(
        stock_code=stock_code, workflow_run_id=workflow_run_id
    )
    return SingleResponse[IndustryDetailsView](data=view)


@router.get(
    "/stocks/{stock_code}/event-impact-ranking",
    response_model=SingleResponse[EventImpactRankingView],
)
def get_event_impact_ranking(
    stock_code: str,
    workflow_run_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> SingleResponse[EventImpactRankingView]:
    view = service.build_event_impact_ranking(
        stock_code=stock_code, workflow_run_id=workflow_run_id, limit=limit
    )
    return SingleResponse[EventImpactRankingView](data=view)


@router.get(
    "/stocks/{stock_code}/benefits-risks",
    response_model=SingleResponse[BenefitsRisksView],
)
def get_benefits_risks(
    stock_code: str,
    workflow_run_id: str | None = Query(None),
) -> SingleResponse[BenefitsRisksView]:
    view = service.build_benefits_risks_view(
        stock_code=stock_code, workflow_run_id=workflow_run_id
    )
    return SingleResponse[BenefitsRisksView](data=view)


# -- Market ----------------------------------------------------------------


@router.get("/market/index-overview", response_model=SingleResponse[IndexOverview])
def get_index_overview(
    refresh: RefreshPolicy = Query(RefreshPolicy.STALE),
) -> SingleResponse[IndexOverview]:
    overview, refresh_task_id = service.build_index_overview(refresh=refresh)
    return SingleResponse[IndexOverview](
        data=overview,
        meta=Meta(refresh_task_id=refresh_task_id),
    )


@router.get("/market/stocks", response_model=SingleResponse[MarketStocksList])
def get_market_stocks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    refresh: RefreshPolicy = Query(RefreshPolicy.STALE),
) -> SingleResponse[MarketStocksList]:
    payload = service.build_market_stocks(
        page=page, page_size=page_size, keyword=keyword, refresh=refresh
    )
    return SingleResponse[MarketStocksList](data=payload)


@router.get("/market/concept-radar", response_model=ListResponse[ConceptRadarItem])
def get_concept_radar(
    limit: int = Query(20, ge=1, le=100),
    refresh: RefreshPolicy = Query(RefreshPolicy.STALE),
) -> ListResponse[ConceptRadarItem]:
    _ = refresh  # accepted; current stub fixtures don't need a refresh task
    items, data_state = service.build_concept_radar(limit=limit)
    return ListResponse[ConceptRadarItem](
        data=items,
        pagination=ListPagination(limit=limit, offset=0, total=len(items), has_more=False),
        meta=Meta(data_state=data_state.value),
    )


@router.get("/market/warnings", response_model=ListResponse[MarketWarning])
def get_market_warnings(
    limit: int = Query(10, ge=1, le=100),
    severity: str | None = Query(None),
    refresh: RefreshPolicy = Query(RefreshPolicy.STALE),
) -> ListResponse[MarketWarning]:
    _ = refresh
    items, data_state = service.build_market_warnings(limit=limit, severity=severity)
    return ListResponse[MarketWarning](
        data=items,
        pagination=ListPagination(limit=limit, offset=0, total=len(items), has_more=False),
        meta=Meta(data_state=data_state.value),
    )
