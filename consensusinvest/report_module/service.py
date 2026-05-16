"""Compatibility exports for Report Module view builders.

Implementation lives in focused modules so this public import path stays stable.
"""

from __future__ import annotations

from .market_views import (
    build_concept_radar,
    build_index_intraday,
    build_index_overview,
    build_market_stocks,
    build_market_warnings,
)
from .runtime_reader import ReportRuntimeReader
from .stock_views import (
    build_benefits_risks_view,
    build_event_impact_ranking,
    build_industry_details_view,
    build_stock_analysis_view,
    build_stock_search,
)

__all__ = [
    "ReportRuntimeReader",
    "build_benefits_risks_view",
    "build_concept_radar",
    "build_event_impact_ranking",
    "build_index_intraday",
    "build_index_overview",
    "build_industry_details_view",
    "build_market_stocks",
    "build_market_warnings",
    "build_stock_analysis_view",
    "build_stock_search",
]
