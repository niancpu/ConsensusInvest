from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
import importlib
import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
from threading import Lock
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import requests

from .models import SearchResultItem, SearchTask


_IPV4_DNS_LOCK = Lock()
_EASTMONEY_INDEX_INTRADAY_ENDPOINTS = (
    "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
    "https://80.push2.eastmoney.com/api/qt/stock/trends2/get",
)
_SINA_INDEX_MINLINE_ENDPOINT = "https://quotes.sina.cn/cn/api/openapi.php/CN_MinlineService.getMinlineData"


@dataclass(frozen=True, slots=True)
class SearchExpansionCandidate:
    action: str
    item: SearchResultItem | dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderSearchResponse:
    items: tuple[SearchResultItem | dict[str, Any], ...] = ()
    expansion_candidates: tuple[SearchExpansionCandidate, ...] = ()
    worker_id: str | None = None
    source_type: str | None = None
    completed_at: str | None = None


class SearchProvider(Protocol):
    def search(self, source: str, task: SearchTask) -> ProviderSearchResponse:
        ...

    def expand(
        self,
        source: str,
        task: SearchTask,
        candidate: SearchExpansionCandidate,
    ) -> ProviderSearchResponse:
        ...


@dataclass(slots=True)
class MockSearchProvider:
    items_by_source: dict[str, tuple[SearchResultItem, ...]] = field(default_factory=dict)
    errors_by_source: dict[str, Exception | str] = field(default_factory=dict)
    expansion_candidates_by_source: dict[str, tuple[SearchExpansionCandidate, ...]] = field(
        default_factory=dict
    )
    expansion_items_by_action: dict[str, tuple[SearchResultItem, ...]] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def search(self, source: str, task: SearchTask) -> ProviderSearchResponse:
        self.calls.append(("search", source))
        self._raise_if_configured(source)
        return ProviderSearchResponse(
            items=self.items_by_source.get(source, ()),
            expansion_candidates=self.expansion_candidates_by_source.get(source, ()),
        )

    def expand(
        self,
        source: str,
        task: SearchTask,
        candidate: SearchExpansionCandidate,
    ) -> ProviderSearchResponse:
        self.calls.append((f"expand:{candidate.action}", source))
        self._raise_if_configured(source)
        return ProviderSearchResponse(items=self.expansion_items_by_action.get(candidate.action, ()))

    def _raise_if_configured(self, source: str) -> None:
        error = self.errors_by_source.get(source)
        if error is None:
            return
        if isinstance(error, Exception):
            raise error
        raise RuntimeError(error)


@dataclass(frozen=True, slots=True)
class HTTPJsonClient:
    timeout_seconds: float = 20.0

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"provider_http_error:{exc.code}:{_trim(error_body, 300)}") from exc
        except URLError as exc:
            raise RuntimeError(f"provider_network_error:{exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("provider_timeout") from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("provider_invalid_json") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("provider_invalid_response")
        return parsed


@dataclass(slots=True)
class TavilySearchProvider:
    api_key: str | None = None
    http_client: Any = field(default_factory=HTTPJsonClient)
    endpoint: str = "https://api.tavily.com/search"
    source: str = "tavily"
    source_type: str = "web_news"
    search_depth: str = "basic"
    include_raw_content: str | bool = "text"
    max_results: int = 5

    @classmethod
    def from_env(cls) -> TavilySearchProvider:
        return cls(
            api_key=os.environ.get("TAVILY_API_KEY"),
            search_depth=os.environ.get("CONSENSUSINVEST_TAVILY_SEARCH_DEPTH", "basic"),
            include_raw_content=os.environ.get(
                "CONSENSUSINVEST_TAVILY_INCLUDE_RAW_CONTENT",
                "text",
            ),
            max_results=_env_int("CONSENSUSINVEST_TAVILY_MAX_RESULTS", 5),
        )

    def search(self, envelope: Any, task: SearchTask) -> ProviderSearchResponse:
        if not self.api_key:
            raise RuntimeError("tavily api key is required: set TAVILY_API_KEY")
        query = _build_query(task)
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": self.search_depth,
            "topic": _tavily_topic(task),
            "max_results": _bounded_max_results(task, default=self.max_results, provider_limit=20),
            "include_answer": False,
            "include_raw_content": _coerce_bool_or_text(self.include_raw_content),
            "include_images": False,
        }
        payload.update(_date_bounds(envelope, task, date_only=True))
        raw_response = self.http_client.post_json(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=payload,
        )
        fetched_at = _now_iso()
        return ProviderSearchResponse(
            items=tuple(
                _tavily_item(
                    result,
                    task=task,
                    query=query,
                    request_payload=payload,
                    provider_response=raw_response,
                    fetched_at=fetched_at,
                    source=self.source,
                    source_type=self.source_type,
                )
                for result in _response_results(raw_response)
            ),
            worker_id=f"search_provider_{self.source}",
            source_type=self.source_type,
            completed_at=fetched_at,
        )

    def expand(
        self,
        envelope: Any,
        task: SearchTask,
        action: str,
        *,
        seed_item: SearchResultItem | dict[str, Any] | None = None,
    ) -> ProviderSearchResponse:
        del envelope, task, action, seed_item
        return ProviderSearchResponse(source_type=self.source_type, completed_at=_now_iso())


@dataclass(slots=True)
class ExaSearchProvider:
    api_key: str | None = None
    http_client: Any = field(default_factory=HTTPJsonClient)
    endpoint: str = "https://api.exa.ai/search"
    source: str = "exa"
    source_type: str = "web_news"
    search_type: str = "auto"
    max_results: int = 5
    include_text: bool = True
    include_highlights: bool = True

    @classmethod
    def from_env(cls) -> ExaSearchProvider:
        return cls(
            api_key=os.environ.get("EXA_API_KEY"),
            search_type=os.environ.get("CONSENSUSINVEST_EXA_SEARCH_TYPE", "auto"),
            max_results=_env_int("CONSENSUSINVEST_EXA_MAX_RESULTS", 5),
            include_text=_env_bool("CONSENSUSINVEST_EXA_INCLUDE_TEXT", True),
            include_highlights=_env_bool("CONSENSUSINVEST_EXA_INCLUDE_HIGHLIGHTS", True),
        )

    def search(self, envelope: Any, task: SearchTask) -> ProviderSearchResponse:
        if not self.api_key:
            raise RuntimeError("exa api key is required: set EXA_API_KEY")
        query = _build_query(task)
        payload: dict[str, Any] = {
            "query": query,
            "type": self.search_type,
            "numResults": _bounded_max_results(task, default=self.max_results, provider_limit=100),
            "contents": {
                "text": self.include_text,
                "highlights": self.include_highlights,
            },
        }
        category = _exa_category(task)
        if category is not None:
            payload["category"] = category
        payload.update(_date_bounds(envelope, task, date_only=False))
        raw_response = self.http_client.post_json(
            self.endpoint,
            headers={"x-api-key": self.api_key},
            payload=payload,
        )
        fetched_at = _now_iso()
        return ProviderSearchResponse(
            items=tuple(
                _exa_item(
                    result,
                    task=task,
                    query=query,
                    request_payload=payload,
                    provider_response=raw_response,
                    fetched_at=fetched_at,
                    source=self.source,
                    source_type=self.source_type,
                )
                for result in _response_results(raw_response)
            ),
            worker_id=f"search_provider_{self.source}",
            source_type=self.source_type,
            completed_at=fetched_at,
        )

    def expand(
        self,
        envelope: Any,
        task: SearchTask,
        action: str,
        *,
        seed_item: SearchResultItem | dict[str, Any] | None = None,
    ) -> ProviderSearchResponse:
        del envelope, task, action, seed_item
        return ProviderSearchResponse(source_type=self.source_type, completed_at=_now_iso())


@dataclass(slots=True)
class AkShareSearchProvider:
    akshare_module: Any = None
    source: str = "akshare"
    source_type: str = "market_data"
    max_results: int = 20

    @classmethod
    def from_env(cls) -> AkShareSearchProvider:
        return cls(max_results=_env_int("CONSENSUSINVEST_AKSHARE_MAX_RESULTS", 20))

    def search(self, envelope: Any, task: SearchTask) -> ProviderSearchResponse:
        akshare = self._require_module()
        ticker = _akshare_symbol(task)
        if not ticker:
            raise RuntimeError("akshare ticker is required: set SearchTask.target.ticker or stock_code")
        fetched_at = _now_iso()
        request_specs = _akshare_request_specs(akshare, envelope, task, ticker)
        if not request_specs:
            evidence_types = ",".join(task.scope.evidence_types) or "unspecified"
            raise RuntimeError(
                "akshare provider has no supported interface for evidence_types: "
                f"{evidence_types}"
            )
        records: list[dict[str, Any]] = []
        for api_name, frame in request_specs:
            records.extend(
                _tag_records(
                    _records_from_frame(frame),
                    provider_api=api_name,
                    provider_symbol=ticker,
                )
            )
        max_results = _bounded_max_results(task, default=self.max_results, provider_limit=200)
        mapper = _akshare_market_snapshot_item if task.task_type == "market_snapshot" else _akshare_item
        items = tuple(
            mapper(
                record,
                envelope=envelope,
                task=task,
                fetched_at=fetched_at,
                source=self.source,
                source_type=self.source_type,
            )
            for record in records[:max_results]
        )
        return ProviderSearchResponse(
            items=items,
            worker_id=f"search_provider_{self.source}",
            source_type=self.source_type,
            completed_at=fetched_at,
        )

    def expand(
        self,
        envelope: Any,
        task: SearchTask,
        action: str,
        *,
        seed_item: SearchResultItem | dict[str, Any] | None = None,
    ) -> ProviderSearchResponse:
        del envelope, task, action, seed_item
        return ProviderSearchResponse(source_type=self.source_type, completed_at=_now_iso())

    def _require_module(self) -> Any:
        if self.akshare_module is not None:
            return self.akshare_module
        try:
            self.akshare_module = importlib.import_module("akshare")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "akshare package is required for source 'akshare': install akshare "
                "or disable CONSENSUSINVEST_AKSHARE_ENABLED"
            ) from exc
        return self.akshare_module


@dataclass(slots=True)
class TuShareSearchProvider:
    token: str | None = None
    tushare_module: Any = None
    pro_client: Any = None
    source: str = "tushare"
    source_type: str = "market_data"
    max_results: int = 20

    @classmethod
    def from_env(cls) -> TuShareSearchProvider:
        return cls(
            token=os.environ.get("CONSENSUSINVEST_TUSHARE_TOKEN")
            or os.environ.get("TUSHARE_TOKEN"),
            max_results=_env_int("CONSENSUSINVEST_TUSHARE_MAX_RESULTS", 20),
        )

    def search(self, envelope: Any, task: SearchTask) -> ProviderSearchResponse:
        pro = self._require_client()
        ts_code = _tushare_ts_code(task)
        if not ts_code:
            raise RuntimeError("tushare ts_code is required: set SearchTask.target.stock_code or ticker")
        fetched_at = _now_iso()
        request_specs = _tushare_request_specs(pro, envelope, task, ts_code)
        if not request_specs:
            evidence_types = ",".join(task.scope.evidence_types) or "unspecified"
            raise RuntimeError(
                "tushare provider has no supported interface for evidence_types: "
                f"{evidence_types}"
            )
        records: list[dict[str, Any]] = []
        for api_name, frame in request_specs:
            records.extend(
                _tag_records(
                    _records_from_frame(frame),
                    provider_api=api_name,
                    provider_symbol=ts_code,
                )
            )
        max_results = _bounded_max_results(task, default=self.max_results, provider_limit=500)
        items = tuple(
            _tushare_item(
                record,
                task=task,
                fetched_at=fetched_at,
                source=self.source,
                source_type=self.source_type,
            )
            for record in records[:max_results]
        )
        return ProviderSearchResponse(
            items=items,
            worker_id=f"search_provider_{self.source}",
            source_type=self.source_type,
            completed_at=fetched_at,
        )

    def expand(
        self,
        envelope: Any,
        task: SearchTask,
        action: str,
        *,
        seed_item: SearchResultItem | dict[str, Any] | None = None,
    ) -> ProviderSearchResponse:
        del envelope, task, action, seed_item
        return ProviderSearchResponse(source_type=self.source_type, completed_at=_now_iso())

    def _require_client(self) -> Any:
        if self.pro_client is not None:
            return self.pro_client
        if not self.token:
            raise RuntimeError(
                "tushare token is required for source 'tushare': set "
                "CONSENSUSINVEST_TUSHARE_TOKEN or TUSHARE_TOKEN"
            )
        if self.tushare_module is None:
            try:
                self.tushare_module = importlib.import_module("tushare")
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "tushare package is required for source 'tushare': install tushare "
                    "or unset CONSENSUSINVEST_TUSHARE_TOKEN/TUSHARE_TOKEN"
                ) from exc
        try:
            self.pro_client = self.tushare_module.pro_api(self.token)
        except Exception as exc:
            raise RuntimeError(f"tushare pro_api initialization failed: {exc}") from exc
        return self.pro_client


def build_real_search_providers_from_env() -> dict[str, SearchProvider]:
    providers: dict[str, SearchProvider] = {}
    if os.environ.get("TAVILY_API_KEY"):
        providers["tavily"] = TavilySearchProvider.from_env()
    if os.environ.get("EXA_API_KEY"):
        providers["exa"] = ExaSearchProvider.from_env()
    if _provider_enabled("CONSENSUSINVEST_AKSHARE_ENABLED", "akshare"):
        providers["akshare"] = AkShareSearchProvider.from_env()
    tushare_enabled = _env_optional_bool("CONSENSUSINVEST_TUSHARE_ENABLED")
    tushare_token = os.environ.get("CONSENSUSINVEST_TUSHARE_TOKEN") or os.environ.get("TUSHARE_TOKEN")
    if tushare_enabled is True or (tushare_enabled is not False and tushare_token):
        providers["tushare"] = TuShareSearchProvider.from_env()
    return providers


def _build_query(task: SearchTask) -> str:
    target = task.target
    parts: list[str] = []
    if target.query:
        parts.append(target.query)
    parts.extend(target.keywords)
    if target.stock_code:
        parts.append(target.stock_code)
    elif target.ticker:
        parts.append(target.ticker)
    parts.extend(_evidence_type_terms(task.scope.evidence_types))
    query = " ".join(_dedupe_text(parts)).strip()
    if not query:
        raise RuntimeError("search query is required")
    return _trim(query, 400)


def _evidence_type_terms(evidence_types: tuple[str, ...]) -> list[str]:
    mapping = {
        "company_news": "公司 新闻",
        "industry_news": "行业 新闻",
        "financial_report": "财报 公告",
        "market_snapshot": "行情",
    }
    return [mapping.get(value, value) for value in evidence_types]


def _tavily_topic(task: SearchTask) -> str:
    evidence_types = set(task.scope.evidence_types)
    if evidence_types & {"company_news", "industry_news"}:
        return "news"
    if evidence_types & {"financial_report", "market_snapshot"}:
        return "finance"
    return "general"


def _exa_category(task: SearchTask) -> str | None:
    evidence_types = set(task.scope.evidence_types)
    if evidence_types & {"company_news", "industry_news"}:
        return "news"
    if "financial_report" in evidence_types:
        return "financial report"
    return None


def _date_bounds(envelope: Any, task: SearchTask, *, date_only: bool) -> dict[str, str]:
    analysis_time = getattr(envelope, "analysis_time", None)
    lookback_days = task.scope.lookback_days
    if analysis_time is None or lookback_days is None or lookback_days <= 0:
        return {}
    end = _as_utc(analysis_time)
    start = end - timedelta(days=lookback_days)
    if date_only:
        return {
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
        }
    return {
        "startPublishedDate": start.isoformat().replace("+00:00", "Z"),
        "endPublishedDate": end.isoformat().replace("+00:00", "Z"),
    }


def _tavily_item(
    result: dict[str, Any],
    *,
    task: SearchTask,
    query: str,
    request_payload: dict[str, Any],
    provider_response: dict[str, Any],
    fetched_at: str,
    source: str,
    source_type: str,
) -> dict[str, Any]:
    url = _clean(result.get("url"))
    content = _clean(result.get("raw_content") or result.get("rawContent") or result.get("content"))
    preview = _clean(result.get("content"))
    score = _score(result.get("score"))
    return {
        "external_id": _external_id(source, result.get("id") or url or result.get("title")),
        "source": source,
        "source_type": source_type,
        "title": _clean(result.get("title")),
        "url": url,
        "content": content,
        "content_preview": preview or _trim(content or "", 500) or None,
        "publish_time": _provider_datetime(result.get("published_date") or result.get("publishedDate")),
        "fetched_at": fetched_at,
        "language": task.constraints.language,
        "raw_payload": {
            "provider_response": result,
            "provider_request": _safe_request_payload(request_payload),
            "provider_request_id": provider_response.get("request_id")
            or provider_response.get("requestId"),
        },
        "source_quality_hint": score,
        "relevance": score,
        "metadata": {
            "query": query,
            "evidence_type": _first_or_none(task.scope.evidence_types),
        },
    }


def _exa_item(
    result: dict[str, Any],
    *,
    task: SearchTask,
    query: str,
    request_payload: dict[str, Any],
    provider_response: dict[str, Any],
    fetched_at: str,
    source: str,
    source_type: str,
) -> dict[str, Any]:
    url = _clean(result.get("url"))
    highlights = result.get("highlights")
    preview = None
    if isinstance(highlights, list) and highlights:
        preview = _clean(highlights[0])
    score = _score(result.get("score"))
    return {
        "external_id": _external_id(source, result.get("id") or url or result.get("title")),
        "source": source,
        "source_type": source_type,
        "title": _clean(result.get("title")),
        "url": url,
        "content": _clean(result.get("text") or result.get("summary")),
        "content_preview": preview or _clean(result.get("summary")),
        "publish_time": _provider_datetime(result.get("publishedDate") or result.get("published_date")),
        "fetched_at": fetched_at,
        "author": _clean(result.get("author")),
        "language": task.constraints.language,
        "raw_payload": {
            "provider_response": result,
            "provider_request": _safe_request_payload(request_payload),
            "provider_request_id": provider_response.get("requestId")
            or provider_response.get("request_id"),
        },
        "source_quality_hint": score,
        "relevance": score,
        "metadata": {
            "query": query,
            "evidence_type": _first_or_none(task.scope.evidence_types),
        },
    }


def _akshare_request_specs(
    akshare: Any,
    envelope: Any,
    task: SearchTask,
    ticker: str,
) -> list[tuple[str, Any]]:
    evidence_types = set(task.scope.evidence_types)
    start_date, end_date = _date_bounds_yyyymmdd(envelope, task)
    specs: list[tuple[str, Any]] = []
    market_view = _market_view(task)
    if not evidence_types or evidence_types & {"company_news", "industry_news"}:
        specs.append(("stock_news_em", _call_provider_method(akshare, "stock_news_em", symbol=ticker)))
    if evidence_types & {"financial_report"}:
        specs.append(
            (
                "stock_financial_abstract",
                _call_provider_method(akshare, "stock_financial_abstract", symbol=ticker),
            )
        )
    if evidence_types & {"market_snapshot", "index_quote"} and (
        market_view in {"index_overview", "index_intraday"} or task.target.entity_type == "market"
    ):
        if market_view == "index_intraday":
            specs.append(_akshare_index_intraday_spec(akshare, task, ticker))
        elif callable(getattr(akshare, "stock_zh_index_spot_em", None)):
            specs.append(("stock_zh_index_spot_em", _call_provider_method(akshare, "stock_zh_index_spot_em")))
    elif evidence_types & {"market_snapshot"}:
        specs.append(
            (
                "stock_zh_a_hist",
                _call_provider_method(
                    akshare,
                    "stock_zh_a_hist",
                    symbol=ticker,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="",
                ),
            )
        )
    return [(name, frame) for name, frame in specs if frame is not _MISSING_PROVIDER_METHOD]


def _akshare_index_intraday_spec(akshare: Any, task: SearchTask, ticker: str) -> tuple[str, Any]:
    akshare_error: RuntimeError | None = None
    if callable(getattr(akshare, "index_zh_a_hist_min_em", None)):
        try:
            return (
                "index_zh_a_hist_min_em",
                _call_provider_method(akshare, "index_zh_a_hist_min_em", symbol=ticker, period="1"),
            )
        except RuntimeError as exc:
            akshare_error = exc
    try:
        return ("eastmoney_index_trends2", _eastmoney_index_intraday_records(task, ticker))
    except RuntimeError as eastmoney_error:
        try:
            return ("sina_index_minline", _sina_index_intraday_records(task, ticker))
        except RuntimeError as sina_error:
            pass
        if akshare_error is not None:
            raise RuntimeError(
                "index intraday provider calls failed: "
                f"akshare={akshare_error}; eastmoney={eastmoney_error}; sina={sina_error}"
            ) from sina_error
        raise RuntimeError(
            "index intraday provider calls failed: "
            f"eastmoney={eastmoney_error}; sina={sina_error}"
        ) from sina_error


def _tushare_request_specs(
    pro: Any,
    envelope: Any,
    task: SearchTask,
    ts_code: str,
) -> list[tuple[str, Any]]:
    evidence_types = set(task.scope.evidence_types)
    start_date, end_date = _date_bounds_yyyymmdd(envelope, task)
    specs: list[tuple[str, Any]] = []
    if not evidence_types or evidence_types & {"market_snapshot"}:
        specs.append(
            (
                "daily_basic",
                _call_provider_method(
                    pro,
                    "daily_basic",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                ),
            )
        )
    if evidence_types & {"financial_report"}:
        specs.append(
            (
                "fina_indicator",
                _call_provider_method(
                    pro,
                    "fina_indicator",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                ),
            )
        )
    return [(name, frame) for name, frame in specs if frame is not _MISSING_PROVIDER_METHOD]


def _akshare_item(
    record: dict[str, Any],
    *,
    envelope: Any,
    task: SearchTask,
    fetched_at: str,
    source: str,
    source_type: str,
) -> dict[str, Any]:
    safe_record = _json_safe(record)
    api_name = _clean(record.get("_provider_api")) or "akshare"
    symbol = _clean(record.get("_provider_symbol")) or _a_share_ticker(task)
    title = _first_clean(
        record,
        ("新闻标题", "标题", "title", "name", "股票简称", "简称", "日期"),
    )
    content = _first_clean(record, ("新闻内容", "内容", "content", "摘要", "summary"))
    if content is None:
        content = json.dumps(safe_record, ensure_ascii=False, default=str)
    url = _first_clean(record, ("新闻链接", "链接", "url", "URL"))
    publish_time = _provider_datetime(
        _first_clean(record, ("发布时间", "日期", "时间", "publish_time", "published_at"))
    )
    source_locator = url or f"akshare://{api_name}/{symbol or 'unknown'}"
    return {
        "external_id": _external_id(source, f"{api_name}:{symbol}:{safe_record}"),
        "source": source,
        "source_type": source_type,
        "title": title or f"AkShare {api_name} {symbol or ''}".strip(),
        "url": source_locator,
        "content": content,
        "content_preview": _trim(content, 500),
        "publish_time": publish_time,
        "fetched_at": fetched_at,
        "author": _first_clean(record, ("文章来源", "来源", "author")),
        "language": task.constraints.language,
        "raw_payload": {
            "provider_response": safe_record,
            "provider_api": api_name,
            "provider_symbol": symbol,
        },
        "source_quality_hint": 0.75,
        "metadata": {
            "evidence_type": _first_or_none(task.scope.evidence_types),
            "provider_api": api_name,
        },
    }


def _akshare_market_snapshot_item(
    record: dict[str, Any],
    *,
    envelope: Any,
    task: SearchTask,
    fetched_at: str,
    source: str,
    source_type: str,
) -> dict[str, Any]:
    safe_record = _json_safe(record)
    api_name = _clean(record.get("_provider_api")) or "akshare"
    symbol = _clean(record.get("_provider_symbol")) or _akshare_symbol(task) or "000001"
    market_view = _market_view(task)
    is_index = "index" in api_name or market_view in {"index_overview", "index_intraday"}
    if is_index:
        code = _index_code_from_record(record, task, symbol)
        name = _first_clean(record, ("名称", "指数名称", "name", "简称")) or _index_name(code)
        value = _first_number(record, ("最新价", "最新", "收盘", "收盘价", "close", "price", "value"))
        change_rate = _first_number(record, ("涨跌幅", "涨跌幅%", "change_rate", "pct_chg"))
        metrics = {
            "code": code,
            "name": name,
            "value": value or 0.0,
            "change": _first_number(record, ("涨跌额", "涨跌", "change")),
            "change_rate": change_rate or 0.0,
            "is_up": (change_rate or 0.0) >= 0,
            "open": _first_number(record, ("今开", "开盘", "open")),
            "high": _first_number(record, ("最高", "high")),
            "low": _first_number(record, ("最低", "low")),
            "previous_close": _first_number(record, ("昨收", "previous_close", "昨收价")),
            "volume": _first_number(record, ("成交量", "volume", "vol")),
            "amount": _first_number(record, ("成交额", "amount")),
        }
        return {
            "external_id": _external_id(source, f"{api_name}:{code}:{safe_record}"),
            "source": source,
            "source_type": source_type,
            "snapshot_type": "index_quote",
            "ticker": code.split(".", 1)[0],
            "snapshot_time": _akshare_snapshot_time(record, envelope),
            "fetched_at": fetched_at,
            "metrics": {key: value for key, value in metrics.items() if value is not None},
            "raw_payload": {
                "provider_response": safe_record,
                "provider_api": api_name,
                "provider_symbol": symbol,
            },
        }

    close_value = _first_number(record, ("收盘", "收盘价", "close", "最新价", "price"))
    change_rate = _first_number(record, ("涨跌幅", "change_rate", "pct_chg"))
    metrics = {
        "stock_code": _stock_code_from_task(task, symbol),
        "ticker": symbol,
        "name": _first_clean(record, ("名称", "股票简称", "简称", "name")) or symbol,
        "price": close_value or 0.0,
        "change_rate": change_rate or 0.0,
        "is_up": (change_rate or 0.0) >= 0,
        "open": _first_number(record, ("开盘", "open")),
        "high": _first_number(record, ("最高", "high")),
        "low": _first_number(record, ("最低", "low")),
        "volume": _first_number(record, ("成交量", "volume", "vol")),
        "amount": _first_number(record, ("成交额", "amount")),
    }
    return {
        "external_id": _external_id(source, f"{api_name}:{symbol}:{safe_record}"),
        "source": source,
        "source_type": source_type,
        "snapshot_type": "stock_quote",
        "ticker": symbol,
        "entity_ids": (task.target.entity_id,) if task.target.entity_id else (),
        "snapshot_time": _akshare_snapshot_time(record, envelope),
        "fetched_at": fetched_at,
        "metrics": {key: value for key, value in metrics.items() if value is not None},
        "raw_payload": {
            "provider_response": safe_record,
            "provider_api": api_name,
            "provider_symbol": symbol,
        },
    }


def _tushare_item(
    record: dict[str, Any],
    *,
    task: SearchTask,
    fetched_at: str,
    source: str,
    source_type: str,
) -> dict[str, Any]:
    safe_record = _json_safe(record)
    api_name = _clean(record.get("_provider_api")) or "tushare"
    ts_code = _clean(record.get("_provider_symbol")) or _tushare_ts_code(task)
    date_value = _first_clean(record, ("ann_date", "trade_date", "end_date", "report_date"))
    content = json.dumps(safe_record, ensure_ascii=False, default=str)
    source_locator = f"tushare://{api_name}/{ts_code or 'unknown'}"
    if date_value:
        source_locator = f"{source_locator}/{date_value}"
    return {
        "external_id": _external_id(source, f"{api_name}:{ts_code}:{safe_record}"),
        "source": source,
        "source_type": source_type,
        "title": f"TuShare {api_name} {ts_code or ''} {date_value or ''}".strip(),
        "url": source_locator,
        "content": content,
        "content_preview": _trim(content, 500),
        "publish_time": _provider_datetime(_compact_date(date_value)),
        "fetched_at": fetched_at,
        "language": task.constraints.language,
        "raw_payload": {
            "provider_response": safe_record,
            "provider_api": api_name,
            "provider_symbol": ts_code,
        },
        "source_quality_hint": 0.8,
        "metadata": {
            "evidence_type": _first_or_none(task.scope.evidence_types),
            "provider_api": api_name,
        },
    }


def _bounded_max_results(task: SearchTask, *, default: int, provider_limit: int) -> int:
    requested = task.scope.max_results if task.scope.max_results is not None else default
    return max(1, min(int(requested), provider_limit))


def _response_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    results = response.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


_MISSING_PROVIDER_METHOD = object()


def _call_provider_method(provider: Any, name: str, **kwargs: Any) -> Any:
    method = getattr(provider, name, None)
    if not callable(method):
        return _MISSING_PROVIDER_METHOD
    try:
        return method(**kwargs)
    except TypeError as exc:
        compact_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            return method(**compact_kwargs)
        except TypeError:
            raise RuntimeError(f"{name} provider call failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"{name} provider call failed: {exc}") from exc


def _records_from_frame(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        if all(isinstance(item, list | tuple) for item in value.values()):
            keys = list(value)
            length = max((len(value[key]) for key in keys), default=0)
            return [
                {key: value[key][index] if index < len(value[key]) else None for key in keys}
                for index in range(length)
            ]
        return [value]
    if isinstance(value, list | tuple):
        return [item for item in value if isinstance(item, dict)]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        records = to_dict("records")
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    return []


def _eastmoney_index_intraday_records(task: SearchTask, ticker: str) -> list[dict[str, Any]]:
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "iscr": "0",
        "iscca": "0",
        "ndays": "1",
    }
    errors: list[str] = []
    for endpoint in _EASTMONEY_INDEX_INTRADAY_ENDPOINTS:
        for secid in _eastmoney_index_secids(task, ticker):
            payload = dict(params, secid=secid)
            try:
                response = _eastmoney_get_json(endpoint, payload)
            except RuntimeError as exc:
                errors.append(f"{endpoint} {secid}:{exc}")
                continue
            data = response.get("data")
            if not isinstance(data, dict):
                errors.append(f"{endpoint} {secid}:empty_data")
                continue
            trends = data.get("trends")
            if not isinstance(trends, list) or not trends:
                errors.append(f"{endpoint} {secid}:empty_trends")
                continue
            records = [
                record
                for item in trends
                if isinstance(item, str) and (record := _eastmoney_index_trend_record(item, data)) is not None
            ]
            if records:
                return records
            errors.append(f"{endpoint} {secid}:invalid_trends")
    detail = "; ".join(errors) if errors else "no secid candidates"
    raise RuntimeError(f"eastmoney index intraday request failed: {detail}")


def _eastmoney_get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        ),
    }
    session = requests.Session()
    session.trust_env = False
    try:
        with _IPV4_DNS_LOCK:
            response = _requests_get_ipv4(session, url, params=params, headers=headers, timeout=20.0)
        response.raise_for_status()
        raw = response.text
    except requests.Timeout as exc:
        raw = _eastmoney_get_json_with_curl(url, params, headers, f"timeout:{exc}")
    except requests.RequestException as exc:
        raw = _eastmoney_get_json_with_curl(url, params, headers, f"network_error:{exc}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid_json") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("invalid_response")
    return parsed


def _eastmoney_get_json_with_curl(
    url: str,
    params: dict[str, str],
    headers: dict[str, str],
    request_error: str,
) -> str:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if curl is None:
        raise RuntimeError(f"{request_error}; curl_unavailable")
    command = [
        curl,
        "-4",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        "20",
    ]
    for key, value in headers.items():
        command.extend(["-H", f"{key}: {value}"])
    command.append(f"{url}?{urlencode(params)}")
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{request_error}; curl_failed:{exc}") from exc
    if completed.stdout:
        return completed.stdout
    if completed.returncode != 0:
        detail = _trim(completed.stderr.strip(), 300)
        raise RuntimeError(f"{request_error}; curl_exit_{completed.returncode}:{detail}")
    else:
        raise RuntimeError(f"{request_error}; curl_empty_response")


def _requests_get_ipv4(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, str],
    headers: dict[str, str],
    timeout: float,
) -> requests.Response:
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo_ipv4(*args: Any, **kwargs: Any) -> list[Any]:
        results = original_getaddrinfo(*args, **kwargs)
        ipv4_results = [item for item in results if item[0] == socket.AF_INET]
        return ipv4_results or results

    socket.getaddrinfo = getaddrinfo_ipv4
    try:
        return session.get(url, params=params, headers=headers, timeout=timeout)
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _eastmoney_index_secids(task: SearchTask, ticker: str) -> tuple[str, ...]:
    raw_code = _clean(task.target.metadata.get("code")) or ticker
    code = raw_code.upper().strip()
    if "." in code:
        raw, suffix = code.split(".", 1)
        if suffix == "SH":
            return (f"1.{raw}",)
        if suffix == "SZ":
            return (f"0.{raw}",)
    if code.startswith("SH"):
        return (f"1.{code.removeprefix('SH')}",)
    if code.startswith("SZ"):
        return (f"0.{code.removeprefix('SZ')}",)
    if ticker in {"399001", "399006"}:
        return (f"0.{ticker}", f"1.{ticker}")
    if ticker == "000001":
        return ("1.000001", "0.000001")
    return (f"1.{ticker}", f"0.{ticker}", f"2.{ticker}", f"47.{ticker}")


def _eastmoney_index_trend_record(raw: str, data: dict[str, Any]) -> dict[str, Any] | None:
    parts = raw.split(",")
    if len(parts) < 8:
        return None
    date_part, _, time_part = parts[0].partition(" ")
    close_value = _number(parts[2])
    previous_close = _number(data.get("preClose"))
    change = close_value - previous_close if close_value is not None and previous_close else None
    change_rate = change / previous_close * 100 if change is not None and previous_close else None
    return {
        "日期": date_part,
        "时间": time_part or parts[0],
        "代码": data.get("code"),
        "名称": data.get("name"),
        "开盘": parts[1],
        "收盘": parts[2],
        "最高": parts[3],
        "最低": parts[4],
        "成交量": parts[5],
        "成交额": parts[6],
        "均价": parts[7],
        "涨跌额": change,
        "涨跌幅": change_rate,
        "昨收": previous_close,
    }


def _sina_index_intraday_records(task: SearchTask, ticker: str) -> list[dict[str, Any]]:
    symbol = _sina_index_symbol(task, ticker)
    response = _sina_get_json(_SINA_INDEX_MINLINE_ENDPOINT, {"symbol": symbol})
    result = response.get("result")
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, list) or not data:
        raise RuntimeError("sina index intraday returned empty data")
    trade_date = _sina_trade_date(task, symbol)
    records = [
        record
        for item in data
        if isinstance(item, dict)
        and (record := _sina_index_minline_record(item, task=task, ticker=ticker, trade_date=trade_date)) is not None
    ]
    if not records:
        raise RuntimeError("sina index intraday returned no usable records")
    return records


def _sina_get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(
            url,
            params=params,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://finance.sina.com.cn/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError(f"sina_timeout:{exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"sina_network_error:{exc}") from exc
    try:
        parsed = response.json()
    except ValueError as exc:
        raise RuntimeError("sina_invalid_json") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("sina_invalid_response")
    return parsed


def _sina_index_symbol(task: SearchTask, ticker: str) -> str:
    raw_code = _clean(task.target.metadata.get("code")) or ticker
    code = raw_code.upper().strip()
    if "." in code:
        raw, suffix = code.split(".", 1)
        return f"{suffix.lower()}{raw}"
    if code.startswith(("SH", "SZ")):
        return code.lower()
    prefix = "sh" if ticker.startswith(("0", "5", "6", "9")) else "sz"
    return f"{prefix}{ticker}"


def _sina_trade_date(task: SearchTask, symbol: str) -> str:
    raw_date = _clean(task.scope.metadata.get("trade_date") or task.target.metadata.get("trade_date"))
    if raw_date:
        return _compact_date(raw_date) or raw_date
    try:
        quote = _sina_get_quote(symbol)
    except RuntimeError:
        return datetime.now().date().isoformat()
    return quote.get("date") or datetime.now().date().isoformat()


def _sina_get_quote(symbol: str) -> dict[str, str]:
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(
            "https://hq.sinajs.cn/list=" + symbol,
            headers={
                "Referer": "https://finance.sina.com.cn/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"sina_quote_network_error:{exc}") from exc
    text = response.text
    _, _, payload = text.partition('="')
    payload = payload.rsplit('";', 1)[0]
    parts = payload.split(",")
    if len(parts) < 31:
        raise RuntimeError("sina_quote_invalid_response")
    date_value = _compact_date(parts[30])
    if date_value is None:
        raise RuntimeError("sina_quote_missing_date")
    return {"date": date_value}


def _sina_index_minline_record(
    item: dict[str, Any],
    *,
    task: SearchTask,
    ticker: str,
    trade_date: str,
) -> dict[str, Any] | None:
    time_value = _clean(item.get("m"))
    price = _number(item.get("p"))
    if time_value is None or price is None:
        return None
    raw_code = _clean(task.target.metadata.get("code")) or ticker
    code = _index_code_from_record({"code": raw_code}, task, ticker)
    return {
        "日期": trade_date,
        "时间": time_value,
        "代码": code,
        "名称": _index_name(code),
        "收盘": price,
        "开盘": price,
        "最高": price,
        "最低": price,
        "成交量": _number(item.get("v")),
        "成交额": _number(item.get("tot_v")),
        "均价": _number(item.get("avg_p")),
        "涨跌幅": _number(item.get("hlz")),
    }


def _tag_records(
    records: list[dict[str, Any]],
    *,
    provider_api: str,
    provider_symbol: str,
) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["_provider_api"] = provider_api
        item["_provider_symbol"] = provider_symbol
        tagged.append(item)
    return tagged


def _safe_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key.lower() not in {"api_key", "apikey"}}


def _external_id(source: str, value: Any) -> str:
    text = str(value or "").strip()
    digest = sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{source}_{digest}"


def _score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(score, 1.0))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _provider_datetime(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return _clean(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _date_bounds_yyyymmdd(envelope: Any, task: SearchTask) -> tuple[str | None, str | None]:
    analysis_time = getattr(envelope, "analysis_time", None)
    if analysis_time is None:
        return None, None
    end = _as_utc(analysis_time)
    lookback_days = task.scope.lookback_days
    if lookback_days is None or lookback_days <= 0:
        return None, end.strftime("%Y%m%d")
    start = end - timedelta(days=lookback_days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _akshare_symbol(task: SearchTask) -> str | None:
    ticker = _a_share_ticker(task)
    if ticker:
        return ticker
    metadata_code = _clean(task.target.metadata.get("code"))
    if metadata_code:
        return metadata_code.split(".", 1)[0].removeprefix("SH").removeprefix("SZ")
    metadata_ticker = _clean(task.target.metadata.get("ticker"))
    if metadata_ticker:
        return metadata_ticker.split(".", 1)[0]
    if task.target.entity_type == "market":
        return "000001"
    return None


def _a_share_ticker(task: SearchTask) -> str | None:
    if task.target.ticker:
        return task.target.ticker.strip()
    if task.target.stock_code:
        return task.target.stock_code.split(".", 1)[0].strip()
    return None


def _tushare_ts_code(task: SearchTask) -> str | None:
    if task.target.stock_code:
        text = task.target.stock_code.strip().upper()
        if "." in text:
            return text
    ticker = _a_share_ticker(task)
    if not ticker:
        return None
    suffix = "SH" if ticker.startswith(("5", "6", "9")) else "SZ"
    return f"{ticker}.{suffix}"


def _market_view(task: SearchTask) -> str | None:
    value = task.target.metadata.get("market_view") or task.scope.metadata.get("market_view") or task.metadata.get("market_view")
    return _clean(value)


def _index_code_from_record(record: dict[str, Any], task: SearchTask, symbol: str) -> str:
    raw = _first_clean(record, ("代码", "指数代码", "code", "symbol")) or task.target.metadata.get("code") or symbol
    text = str(raw).strip().upper()
    if text in {"000001", "SH000001"}:
        return "000001.SH"
    if text in {"399001", "SZ399001"}:
        return "399001.SZ"
    if text in {"399006", "SZ399006"}:
        return "399006.SZ"
    if "." in text:
        return text
    suffix = "SH" if text.startswith(("0", "5", "6", "9")) else "SZ"
    return f"{text}.{suffix}"


def _index_name(code: str) -> str:
    return {
        "000001.SH": "上证指数",
        "399001.SZ": "深证成指",
        "399006.SZ": "创业板指",
    }.get(code, code)


def _stock_code_from_task(task: SearchTask, symbol: str) -> str:
    if task.target.stock_code:
        return task.target.stock_code.strip().upper()
    suffix = "SH" if symbol.startswith(("5", "6", "9")) else "SZ"
    return f"{symbol}.{suffix}"


def _first_number(record: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number(record.get(key))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    text = text.replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _akshare_snapshot_time(record: dict[str, Any], envelope: Any) -> str:
    date_value = _first_clean(record, ("日期", "date", "trade_date"))
    time_value = _first_clean(record, ("时间", "time", "datetime"))
    if date_value and len(date_value) == 8 and date_value.isdigit():
        date_value = _compact_date(date_value)
    if date_value and time_value and "T" not in time_value:
        return _provider_datetime(f"{date_value} {time_value}") or _now_iso()
    if date_value:
        return _provider_datetime(date_value) or _now_iso()
    if time_value:
        analysis_time = getattr(envelope, "analysis_time", None)
        if isinstance(analysis_time, datetime):
            return _provider_datetime(f"{analysis_time.date().isoformat()} {time_value}") or _now_iso()
        return _provider_datetime(time_value) or _now_iso()
    analysis_time = getattr(envelope, "analysis_time", None)
    if isinstance(analysis_time, datetime):
        return analysis_time.isoformat()
    return _now_iso()


def _first_clean(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _clean(record.get(key))
        if value is not None:
            return value
    return None


def _compact_date(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    return value


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip()


def _first_or_none(values: tuple[str, ...]) -> str | None:
    return values[0] if values else None


def _dedupe_text(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _coerce_bool_or_text(value: str | bool) -> str | bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    coerced = _coerce_bool_or_text(raw)
    if isinstance(coerced, bool):
        return coerced
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _provider_enabled(env_name: str, module_name: str) -> bool:
    configured = _env_optional_bool(env_name)
    if configured is not None:
        return configured
    return _module_available(module_name)


def _env_optional_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False
