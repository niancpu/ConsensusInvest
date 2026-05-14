from fastapi.testclient import TestClient

from consensusinvest.app import create_app


def test_agent_runs_api() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/workflow-runs/wr_20260513_002594_000001/agent-runs")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["request_id"].startswith("req_")
    row = body["data"][0]
    assert row["workflow_run_id"] == "wr_20260513_002594_000001"
    assert row["status"] == "completed"
    assert isinstance(row["rounds"], list)


def test_agent_arguments_filter_detail_and_references() -> None:
    client = TestClient(create_app())
    response = client.get(
        "/api/v1/workflow-runs/wr_20260513_002594_000001/agent-arguments",
        params={"agent_id": "bull_v1", "round": 1},
    )

    assert response.status_code == 200, response.text
    argument = response.json()["data"][0]
    assert argument["agent_id"] == "bull_v1"
    assert argument["round"] == 1
    assert isinstance(argument["role_output"], dict)

    detail = client.get(f"/api/v1/agent-arguments/{argument['agent_argument_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["agent_argument_id"] == argument["agent_argument_id"]

    refs = client.get(f"/api/v1/agent-arguments/{argument['agent_argument_id']}/references")
    assert refs.status_code == 200, refs.text
    for ref in refs.json()["data"]:
        assert ref["source_type"] == "agent_argument"
        assert ref["source_id"] == argument["agent_argument_id"]
        assert ref["reference_role"] in {"supports", "counters"}


def test_round_summaries_api() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/workflow-runs/wr_20260513_002594_000001/round-summaries")

    assert response.status_code == 200, response.text
    summary = response.json()["data"][0]
    assert summary["workflow_run_id"] == "wr_20260513_002594_000001"
    assert summary["participants"] == ["bull_v1"]
    assert summary["agent_argument_ids"]
    assert summary["referenced_evidence_ids"]

    detail = client.get(f"/api/v1/round-summaries/{summary['round_summary_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["round_summary_id"] == summary["round_summary_id"]


def test_judgment_references_and_tool_calls_api() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/workflow-runs/wr_20260513_002594_000001/judgment")

    assert response.status_code == 200, response.text
    judgment = response.json()["data"]
    assert judgment["judgment_id"] == "jdg_20260513_002594_001"
    assert judgment["final_signal"] in {"bullish", "neutral", "bearish"}
    assert judgment["links"]["references"].endswith("/references")
    assert judgment["links"]["trace"].endswith("/trace")

    detail = client.get(f"/api/v1/judgments/{judgment['judgment_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["workflow_run_id"] == "wr_20260513_002594_000001"

    refs = client.get(f"/api/v1/judgments/{judgment['judgment_id']}/references")
    assert refs.status_code == 200, refs.text
    for ref in refs.json()["data"]:
        assert ref["source_type"] == "judgment"
        assert ref["evidence_id"].startswith("ev_")
        assert ref["reference_role"] in {"supports", "counters"}

    tool_calls = client.get(f"/api/v1/judgments/{judgment['judgment_id']}/tool-calls")
    assert tool_calls.status_code == 200, tool_calls.text
    call = tool_calls.json()["data"][0]
    assert call["tool_name"] == "get_evidence_detail"
    assert isinstance(call["input"], dict)
    assert isinstance(call["output_summary"], str)
    assert all(evidence_id.startswith("ev_") for evidence_id in call["referenced_evidence_ids"])


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
