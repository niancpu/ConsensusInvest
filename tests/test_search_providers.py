from datetime import datetime, timezone

import pytest

from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent import (
    ExaSearchProvider,
    TavilySearchProvider,
    build_real_search_providers_from_env,
)
from consensusinvest.search_agent.models import SearchTask


class FakeHTTPClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, *, headers, payload):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        return self.response


def make_envelope():
    return InternalCallEnvelope(
        request_id="req_provider_001",
        correlation_id="corr_provider_001",
        workflow_run_id="wr_provider_001",
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="workflow_orchestrator",
        idempotency_key="search_provider_001",
    )


def make_task(*, max_results=3):
    return SearchTask(
        task_type="stock_research",
        target={
            "ticker": "002594",
            "stock_code": "002594.SZ",
            "entity_id": "ent_company_002594",
            "keywords": ["比亚迪", "BYD"],
        },
        scope={
            "sources": ["tavily"],
            "evidence_types": ["company_news"],
            "lookback_days": 30,
            "max_results": max_results,
        },
        constraints={
            "language": "zh-CN",
            "expansion_policy": {"allowed": False, "max_depth": 0, "allowed_actions": []},
            "budget": {"max_provider_calls": 1, "max_runtime_ms": 60000},
        },
        callback={"ingest_target": "evidence_store", "workflow_run_id": "wr_provider_001"},
        idempotency_key="search_provider_001",
    )


def test_tavily_provider_posts_constrained_query_and_maps_results():
    http = FakeHTTPClient(
        {
            "request_id": "tv_req_001",
            "results": [
                {
                    "title": "比亚迪发布经营更新",
                    "url": "https://example.com/byd/update",
                    "content": "比亚迪发布经营更新摘要。",
                    "raw_content": "比亚迪发布经营更新原文。",
                    "published_date": "2026-05-12T09:00:00+00:00",
                    "score": 0.87,
                }
            ],
        }
    )
    provider = TavilySearchProvider(api_key="tv_key", http_client=http, max_results=5)

    response = provider.search(make_envelope(), make_task(max_results=2))

    assert http.calls[0]["url"] == "https://api.tavily.com/search"
    assert http.calls[0]["headers"]["Authorization"] == "Bearer tv_key"
    payload = http.calls[0]["payload"]
    assert "比亚迪" in payload["query"]
    assert "company_news" not in payload["query"]
    assert payload["topic"] == "news"
    assert payload["max_results"] == 2
    assert payload["start_date"] == "2026-04-13"
    assert payload["end_date"] == "2026-05-13"

    item = response.items[0]
    assert item["source"] == "tavily"
    assert item["source_type"] == "web_news"
    assert item["title"] == "比亚迪发布经营更新"
    assert item["content"] == "比亚迪发布经营更新原文。"
    assert item["content_preview"] == "比亚迪发布经营更新摘要。"
    assert item["publish_time"] == "2026-05-12T09:00:00+00:00"
    assert item["language"] == "zh-CN"
    assert item["source_quality_hint"] == 0.87
    assert item["metadata"]["evidence_type"] == "company_news"
    assert item["raw_payload"]["provider_response"]["url"] == "https://example.com/byd/update"
    assert item["raw_payload"]["provider_request"]["query"] == payload["query"]


def test_tavily_provider_normalizes_http_date_publish_time():
    http = FakeHTTPClient(
        {
            "results": [
                {
                    "title": "BYD update",
                    "url": "https://example.com/byd/http-date",
                    "content": "BYD update.",
                    "published_date": "Mon, 11 May 2026 22:00:29 GMT",
                    "score": 0.8,
                }
            ],
        }
    )
    provider = TavilySearchProvider(api_key="tv_key", http_client=http)

    response = provider.search(make_envelope(), make_task(max_results=1))

    assert response.items[0]["publish_time"] == "2026-05-11T22:00:29+00:00"


def test_exa_provider_posts_constrained_query_and_maps_results():
    http = FakeHTTPClient(
        {
            "requestId": "exa_req_001",
            "results": [
                {
                    "id": "exa_doc_001",
                    "title": "BYD operating update",
                    "url": "https://example.com/byd/exa",
                    "text": "BYD published an operating update.",
                    "highlights": ["Operating update highlight."],
                    "publishedDate": "2026-05-11T12:00:00+00:00",
                    "author": "Example News",
                    "score": 0.91,
                }
            ],
        }
    )
    provider = ExaSearchProvider(api_key="exa_key", http_client=http, max_results=5)

    response = provider.search(make_envelope(), make_task(max_results=4))

    assert http.calls[0]["url"] == "https://api.exa.ai/search"
    assert http.calls[0]["headers"]["x-api-key"] == "exa_key"
    payload = http.calls[0]["payload"]
    assert payload["type"] == "auto"
    assert payload["category"] == "news"
    assert payload["numResults"] == 4
    assert payload["contents"] == {"text": True, "highlights": True}
    assert payload["startPublishedDate"] == "2026-04-13T10:00:00Z"
    assert payload["endPublishedDate"] == "2026-05-13T10:00:00Z"

    item = response.items[0]
    assert item["source"] == "exa"
    assert item["external_id"].startswith("exa_")
    assert item["content"] == "BYD published an operating update."
    assert item["content_preview"] == "Operating update highlight."
    assert item["author"] == "Example News"
    assert item["relevance"] == 0.91
    assert item["raw_payload"]["provider_request_id"] == "exa_req_001"


def test_real_providers_require_api_keys():
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        TavilySearchProvider(api_key=None, http_client=FakeHTTPClient({})).search(
            make_envelope(),
            make_task(),
        )
    with pytest.raises(RuntimeError, match="EXA_API_KEY"):
        ExaSearchProvider(api_key=None, http_client=FakeHTTPClient({})).search(
            make_envelope(),
            make_task(),
        )


def test_env_factory_registers_only_configured_real_providers(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    assert build_real_search_providers_from_env() == {}

    monkeypatch.setenv("TAVILY_API_KEY", "tv_key")
    monkeypatch.setenv("EXA_API_KEY", "exa_key")
    providers = build_real_search_providers_from_env()
    assert set(providers) == {"tavily", "exa"}
    assert isinstance(providers["tavily"], TavilySearchProvider)
    assert isinstance(providers["exa"], ExaSearchProvider)


def test_env_factory_parses_provider_options(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("EXA_API_KEY", "exa_key")
    monkeypatch.setenv("CONSENSUSINVEST_EXA_INCLUDE_TEXT", "false")
    monkeypatch.setenv("CONSENSUSINVEST_EXA_INCLUDE_HIGHLIGHTS", "0")
    monkeypatch.setenv("CONSENSUSINVEST_EXA_MAX_RESULTS", "9")

    provider = build_real_search_providers_from_env()["exa"]

    assert provider.include_text is False
    assert provider.include_highlights is False
    assert provider.max_results == 9
