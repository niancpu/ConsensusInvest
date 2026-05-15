"""Search Agent task status API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from consensusinvest.app import create_app


def test_search_task_status_returns_queued_market_refresh() -> None:
    client = TestClient(create_app())
    client.app.state.runtime.search_pool.providers = {}

    refresh = client.get("/api/v1/market/index-intraday", params={"code": "000001.SH"})
    assert refresh.status_code == 200, refresh.text
    task_id = refresh.json()["data"]["refresh_task_id"]

    status = client.get(f"/api/v1/search-tasks/{task_id}")
    assert status.status_code == 200, status.text
    data = status.json()["data"]
    assert data["task_id"] == task_id
    assert data["status"] == "queued"
    assert data["source_status"][0]["source"] == "akshare"
    assert data["sources"]["akshare"]["status"] == "queued"


def test_search_task_status_unknown_task_returns_404() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/search-tasks/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SEARCH_TASK_NOT_FOUND"
