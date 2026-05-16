"""Search refresh task helpers for Report Module views."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import Any
from uuid import uuid4

from consensusinvest.entities.repository import EntityRecord
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import (
    SearchBudget,
    SearchCallback,
    SearchConstraints,
    SearchExpansionPolicy,
    SearchScope,
    SearchTarget,
    SearchTask,
)

from ._utils import _dedupe
from .projections import _stock_code, _ticker


logger = logging.getLogger(__name__)

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
    try:
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
    except Exception:
        logger.exception("Failed to submit stock refresh task for ticker=%s report_run_id=%s", ticker, report_run_id)
        return None
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
        metadata=metadata,
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
    try:
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
    except Exception:
        logger.exception(
            "Failed to submit market refresh task for market_view=%s report_run_id=%s",
            market_view,
            report_run_id,
        )
        return None
    return _task_id(receipt)

def _report_refresh_idempotency_key(*, ticker: str, analysis_time: datetime, reason: str) -> str:
    return f"report_refresh_{ticker}_{analysis_time.strftime('%Y%m%d')}_{reason}"

def _market_refresh_idempotency_key(
    *,
    market_view: str,
    analysis_time: datetime,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    qualifiers = _market_refresh_idempotency_qualifiers(market_view, metadata or {})
    suffix = f"_{qualifiers}" if qualifiers else ""
    key = f"report_market_refresh_{analysis_time.strftime('%Y%m%d')}_{market_view}_{reason}{suffix}"
    return key if len(key) <= 240 else f"{key[:207]}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]}"

def _market_refresh_idempotency_qualifiers(market_view: str, metadata: dict[str, Any]) -> str:
    if market_view == "index_intraday":
        return _idempotency_token(metadata.get("code") or metadata.get("ticker"))
    return ""

def _idempotency_token(value: Any) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    return "".join(char if char.isalnum() else "_" for char in token)

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
        try:
            return bool(run_task_once(refresh_task_id))
        except Exception:
            logger.exception("Failed to run refresh task once: task_id=%s", refresh_task_id)
            return False
    run_pending_once = getattr(search_pool, "run_pending_once", None)
    if callable(run_pending_once):
        try:
            return refresh_task_id in set(str(task_id) for task_id in run_pending_once())
        except Exception:
            logger.exception("Failed to run pending refresh tasks for task_id=%s", refresh_task_id)
            return False
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
