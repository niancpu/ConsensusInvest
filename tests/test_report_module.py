"""Smoke tests covering every Report Module HTTP endpoint.

These tests use FastAPI's TestClient against the app factory. They verify the
documented response envelopes (`data`, `meta`, `pagination`) and the boundary
rules from `docs/report_module/`:

- search returns hits with `match` and (optional) `evidence_matches`
- analysis: `report_generation` clears workflow_run_id / judgment_id / action / benefits
- analysis: `with_workflow_trace` carries action.source = main_judgment_summary
- benefits-risks: no judgment ⇒ benefits empty, risks only from risk_disclosure
- event-impact-ranking: direction allowed only when workflow_run_id/judgment_id set
- market endpoints: snapshot_ids / data_state / refresh_task_id semantics
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from consensusinvest.app import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# -- Stock search ----------------------------------------------------------


def test_search_returns_known_stock(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/search", params={"keyword": "比亚迪"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "data" in body and "meta" in body
    assert body["meta"]["request_id"].startswith("req_")
    hits = body["data"]
    assert hits and hits[0]["stock_code"] == "002594.SZ"
    assert hits[0]["entity_id"] == "ent_company_002594"
    assert hits[0]["match"]["type"] in {"entity", "entity_and_evidence"}
    assert isinstance(hits[0]["evidence_matches"], list)


def test_search_keyword_required(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/search")
    assert r.status_code == 400 or r.status_code == 422
    body = r.json()
    # both validator paths should land in the documented error envelope
    assert "error" in body or "detail" in body


def test_search_include_evidence_false_omits_matches(client: TestClient) -> None:
    r = client.get(
        "/api/v1/stocks/search",
        params={"keyword": "比亚迪", "include_evidence": "false"},
    )
    assert r.status_code == 200
    assert r.json()["data"][0]["evidence_matches"] == []


# -- Stock analysis --------------------------------------------------------


def test_analysis_with_workflow_trace(client: TestClient) -> None:
    r = client.get(
        "/api/v1/stocks/002594.SZ/analysis",
        params={"workflow_run_id": "wr_20260513_002594_000001"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["report_mode"] == "with_workflow_trace"
    assert data["workflow_run_id"] == "wr_20260513_002594_000001"
    assert data["judgment_id"] == "jdg_20260513_002594_001"
    assert data["action"]["source"] == "main_judgment_summary"
    assert data["report"]["key_evidence"]
    assert "evidence_ids" in data["trace_refs"]
    assert data["links"]["workflow_run"].endswith(data["workflow_run_id"])


def test_analysis_report_generation_mode_when_no_judgment(client: TestClient) -> None:
    # 600519 has no seeded judgment in repository.py
    r = client.get("/api/v1/stocks/600519.SH/analysis")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["report_mode"] == "report_generation"
    assert data["workflow_run_id"] is None
    assert data["judgment_id"] is None
    assert data.get("action") is None
    assert data["report"]["title"] == "个股研究聚合视图"
    # report_run_id is required for report_generation views
    assert data["report_run_id"].startswith("rpt_")


def test_analysis_unknown_stock_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/999999.XX/analysis")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "STOCK_NOT_FOUND"


# -- Industry details ------------------------------------------------------


def test_industry_details_returns_traceable_refs(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/002594.SZ/industry-details")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["industry_entity_id"] == "ent_industry_new_energy_vehicle"
    assert data["policy_support_level"] in {"low", "medium", "high"}
    assert data["referenced_evidence_ids"]
    assert data["links"]["entity_relations"].endswith("/relations")


# -- Event impact ranking --------------------------------------------------


def test_event_impact_ranking_direction_only_with_trace(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/002594.SZ/event-impact-ranking", params={"limit": 5})
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert items, "expected at least one impact item from the fixture"
    for item in items:
        if item["direction"] is not None:
            assert item["workflow_run_id"] or item["judgment_id"], item


# -- Benefits & risks ------------------------------------------------------


def test_benefits_risks_with_judgment(client: TestClient) -> None:
    r = client.get(
        "/api/v1/stocks/002594.SZ/benefits-risks",
        params={"workflow_run_id": "wr_20260513_002594_000001"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["workflow_run_id"] == "wr_20260513_002594_000001"
    assert data["benefits"], "benefits must surface when judgment exists"
    assert data["benefits"][0]["source"] == "main_judgment_summary"
    assert data["risks"]


def test_benefits_risks_no_judgment_means_empty_benefits(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/600519.SH/benefits-risks")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["workflow_run_id"] is None
    assert data["benefits"] == []
    # risks may still come from evidence_structure_risk_disclosure
    for risk in data["risks"]:
        assert risk["source"] == "evidence_structure_risk_disclosure"


# -- Market: index-overview ------------------------------------------------


def test_index_overview_returns_snapshot_refs(client: TestClient) -> None:
    r = client.get("/api/v1/market/index-overview")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["indices"]
    for idx in data["indices"]:
        assert idx["snapshot_id"].startswith("mkt_snap_")
    assert data["market_sentiment"]["source"] == "market_snapshot_projection"
    assert data["data_state"] in {"ready", "stale", "partial", "pending_refresh"}


# -- Market: stocks --------------------------------------------------------


def test_market_stocks_pagination(client: TestClient) -> None:
    r = client.get(
        "/api/v1/market/stocks",
        params={"page": 1, "page_size": 1},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["page_size"] == 1
    assert len(data["list"]) <= 1
    if data["list"]:
        row = data["list"][0]
        assert row["entity_id"].startswith("ent_company_")
        assert row["snapshot_id"].startswith("mkt_snap_")


def test_market_stocks_keyword_filter(client: TestClient) -> None:
    r = client.get(
        "/api/v1/market/stocks", params={"keyword": "比亚迪", "page": 1, "page_size": 20}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(row["stock_code"] == "002594.SZ" for row in data["list"])


# -- Market: concept-radar -------------------------------------------------


def test_concept_radar(client: TestClient) -> None:
    r = client.get("/api/v1/market/concept-radar", params={"limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["data"], list)
    if body["data"]:
        item = body["data"][0]
        assert item["entity_id"].startswith("ent_concept_")
        assert item["trend"] in {"warming", "cooling", "flat"}
        # evidence_ids may be empty when concept hasn't entered the evidence chain yet
        assert isinstance(item["evidence_ids"], list)


# -- Market: warnings ------------------------------------------------------


def test_warnings_severity_validation(client: TestClient) -> None:
    r = client.get("/api/v1/market/warnings", params={"severity": "bogus"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_warnings_returns_traceable_refs(client: TestClient) -> None:
    r = client.get("/api/v1/market/warnings", params={"severity": "notice"})
    assert r.status_code == 200
    items = r.json()["data"]
    assert items
    item = items[0]
    assert item["warning_id"].startswith("warn_")
    assert item["snapshot_ids"]
    assert item["severity"] == "notice"


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
