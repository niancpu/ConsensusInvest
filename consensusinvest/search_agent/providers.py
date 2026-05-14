from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import SearchResultItem, SearchTask


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


def build_real_search_providers_from_env() -> dict[str, SearchProvider]:
    providers: dict[str, SearchProvider] = {}
    if os.environ.get("TAVILY_API_KEY"):
        providers["tavily"] = TavilySearchProvider.from_env()
    if os.environ.get("EXA_API_KEY"):
        providers["exa"] = ExaSearchProvider.from_env()
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
        "publish_time": _clean(result.get("published_date") or result.get("publishedDate")),
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
        "publish_time": _clean(result.get("publishedDate") or result.get("published_date")),
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


def _bounded_max_results(task: SearchTask, *, default: int, provider_limit: int) -> int:
    requested = task.scope.max_results if task.scope.max_results is not None else default
    return max(1, min(int(requested), provider_limit))


def _response_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    results = response.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


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
