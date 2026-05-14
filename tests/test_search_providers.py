from datetime import datetime, timezone

import pytest

from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent import (
    AkShareSearchProvider,
    ExaSearchProvider,
    TavilySearchProvider,
    TuShareSearchProvider,
    build_real_search_providers_from_env,
)
import consensusinvest.search_agent.providers as provider_module
from consensusinvest.search_agent.models import SearchTask


def test_package_public_entrypoint_does_not_export_mock_provider():
    import consensusinvest.search_agent as search_agent

    assert "MockSearchProvider" not in search_agent.__all__
    assert not hasattr(search_agent, "MockSearchProvider")


class FakeHTTPClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, *, headers, payload):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        return self.response


class FakeFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


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


def test_akshare_provider_maps_optional_module_results():
    class FakeAkShare:
        def stock_news_em(self, *, symbol):
            assert symbol == "002594"
            return FakeFrame(
                [
                    {
                        "新闻标题": "比亚迪新闻",
                        "新闻链接": "https://example.com/akshare/news",
                        "新闻内容": "AkShare 新闻原文。",
                        "发布时间": "2026-05-12 09:30:00",
                        "文章来源": "东方财富",
                    }
                ]
            )

    provider = AkShareSearchProvider(akshare_module=FakeAkShare())

    response = provider.search(make_envelope(), make_task(max_results=1))

    item = response.items[0]
    assert response.source_type == "market_data"
    assert item["source"] == "akshare"
    assert item["source_type"] == "market_data"
    assert item["title"] == "比亚迪新闻"
    assert item["url"] == "https://example.com/akshare/news"
    assert item["content"] == "AkShare 新闻原文。"
    assert item["author"] == "东方财富"
    assert item["raw_payload"]["provider_api"] == "stock_news_em"
    assert item["raw_payload"]["provider_symbol"] == "002594"


def test_tushare_provider_maps_optional_client_results():
    class FakeTuSharePro:
        def daily_basic(self, *, ts_code, start_date, end_date):
            assert ts_code == "002594.SZ"
            assert start_date == "20260413"
            assert end_date == "20260513"
            return FakeFrame(
                [
                    {
                        "ts_code": "002594.SZ",
                        "trade_date": "20260512",
                        "close": 100.5,
                        "turnover_rate": 1.2,
                    }
                ]
            )

    provider = TuShareSearchProvider(pro_client=FakeTuSharePro())
    task = make_task(max_results=1)
    task = SearchTask(
        target=task.target,
        scope={
            "sources": ["tushare"],
            "evidence_types": ["market_snapshot"],
            "lookback_days": 30,
            "max_results": 1,
        },
        constraints=task.constraints,
        callback=task.callback,
        idempotency_key=task.idempotency_key,
        task_type=task.task_type,
    )

    response = provider.search(make_envelope(), task)

    item = response.items[0]
    assert response.source_type == "market_data"
    assert item["source"] == "tushare"
    assert item["url"] == "tushare://daily_basic/002594.SZ/20260512"
    assert item["publish_time"] == "2026-05-12T00:00:00"
    assert '"close": 100.5' in item["content"]
    assert item["raw_payload"]["provider_api"] == "daily_basic"
    assert item["raw_payload"]["provider_symbol"] == "002594.SZ"


def test_env_factory_skips_unconfigured_optional_market_providers(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_AKSHARE_ENABLED", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_TUSHARE_ENABLED", raising=False)
    monkeypatch.delenv("CONSENSUSINVEST_TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(provider_module, "_module_available", lambda name: False)

    assert build_real_search_providers_from_env() == {}


def test_enabled_optional_market_providers_report_missing_dependencies(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("CONSENSUSINVEST_AKSHARE_ENABLED", "true")
    monkeypatch.setenv("CONSENSUSINVEST_TUSHARE_TOKEN", "ts_token")
    monkeypatch.setattr(provider_module, "_module_available", lambda name: False)

    def missing_import(name):
        if name in {"akshare", "tushare"}:
            raise ModuleNotFoundError(name)
        return __import__(name)

    monkeypatch.setattr(provider_module.importlib, "import_module", missing_import)

    providers = build_real_search_providers_from_env()
    assert set(providers) == {"akshare", "tushare"}
    with pytest.raises(RuntimeError, match="akshare package is required"):
        providers["akshare"].search(make_envelope(), make_task(max_results=1))
    with pytest.raises(RuntimeError, match="tushare package is required"):
        providers["tushare"].search(make_envelope(), make_task(max_results=1))
