from fastapi.testclient import TestClient

from consensusinvest.app import create_app


def test_workflow_api_create_detail_snapshot_trace_and_events() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/workflow-runs",
        json={
            "ticker": "002594",
            "analysis_time": "2026-05-13T10:00:00+00:00",
            "workflow_config_id": "mvp_bull_judge_v1",
            "query": {"lookback_days": 30, "sources": ["tavily"]},
            "options": {"stream": True, "include_raw_payload": False, "auto_run": True},
        },
    )

    assert response.status_code == 202, response.text
    created = response.json()["data"]
    workflow_run_id = created["workflow_run_id"]
    assert created["events_url"].endswith("/events")
    assert created["snapshot_url"].endswith("/snapshot")

    detail = client.get(f"/api/v1/workflow-runs/{workflow_run_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["workflow_run_id"] == workflow_run_id
    assert detail.json()["data"]["status"] == "insufficient_evidence"

    listing = client.get("/api/v1/workflow-runs", params={"ticker": "002594"})
    assert listing.status_code == 200, listing.text
    assert any(row["workflow_run_id"] == workflow_run_id for row in listing.json()["data"])

    snapshot = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/snapshot", params={"include_events": True})
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["data"]["workflow_run"]["workflow_run_id"] == workflow_run_id
    assert snapshot.json()["data"]["last_event_sequence"] >= 2
    assert snapshot.json()["data"]["events"]

    trace = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/trace")
    assert trace.status_code == 200, trace.text
    assert trace.json()["data"]["workflow_run_id"] == workflow_run_id
    assert isinstance(trace.json()["data"]["trace_nodes"], list)

    events = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/events")
    assert events.status_code == 200, events.text
    assert "event: workflow_queued" in events.text


def test_workflow_api_not_found_error() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/workflow-runs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKFLOW_RUN_NOT_FOUND"
