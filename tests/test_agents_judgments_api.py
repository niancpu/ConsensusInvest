from fastapi.testclient import TestClient

from consensusinvest.app import create_app


def test_agent_runtime_lists_are_empty_without_seeded_demo_data() -> None:
    client = TestClient(create_app())
    workflow_run_id = "wr_20260513_002594_000001"

    agent_runs = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/agent-runs")
    assert agent_runs.status_code == 200, agent_runs.text
    assert agent_runs.json()["data"] == []

    arguments = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/agent-arguments")
    assert arguments.status_code == 200, arguments.text
    assert arguments.json()["data"] == []

    summaries = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/round-summaries")
    assert summaries.status_code == 200, summaries.text
    assert summaries.json()["data"] == []


def test_workflow_judgment_not_seeded_by_default() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/workflow-runs/wr_20260513_002594_000001/judgment")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JUDGMENT_NOT_FOUND"


def test_agent_judgment_not_found_errors() -> None:
    client = TestClient(create_app())

    arg = client.get("/api/v1/agent-arguments/missing")
    assert arg.status_code == 404
    assert arg.json()["error"]["code"] == "AGENT_ARGUMENT_NOT_FOUND"

    summary = client.get("/api/v1/round-summaries/missing")
    assert summary.status_code == 404
    assert summary.json()["error"]["code"] == "ROUND_SUMMARY_NOT_FOUND"

    judgment = client.get("/api/v1/judgments/missing")
    assert judgment.status_code == 404
    assert judgment.json()["error"]["code"] == "JUDGMENT_NOT_FOUND"
