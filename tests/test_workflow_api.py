from datetime import datetime, timezone

from fastapi.testclient import TestClient

from consensusinvest.app import create_app
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent import SearchAgentPool
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget
from consensusinvest.search_agent.providers import MockSearchProvider
from consensusinvest.workflow_orchestrator.acquisition import EvidenceAcquisitionService
from consensusinvest.workflow_orchestrator.models import WorkflowOptions, WorkflowQuery, WorkflowRunCreate


def _analysis_time() -> datetime:
    return datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)


def _seed_workflow_evidence(workflow_run_id: str, store) -> None:
    store.ingest_search_result(
        InternalCallEnvelope(
            request_id=f"req_seed_{workflow_run_id}",
            correlation_id=f"corr_seed_{workflow_run_id}",
            workflow_run_id=workflow_run_id,
            analysis_time=_analysis_time(),
            requested_by="workflow_orchestrator",
            idempotency_key=f"seed_{workflow_run_id}",
        ),
        SearchResultPackage(
            task_id=f"st_{workflow_run_id}",
            worker_id="worker_tavily",
            source="tavily",
            source_type="web_news",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("BYD",),
            ),
            items=(
                {
                    "external_id": f"{workflow_run_id}_news_001",
                    "title": "BYD margin improved",
                    "url": f"https://example.com/{workflow_run_id}/001",
                    "content": "BYD reported margin improvement.",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "source_quality_hint": 0.86,
                    "metadata": {"evidence_type": "company_news"},
                },
                {
                    "external_id": f"{workflow_run_id}_news_002",
                    "title": "BYD cash flow needs checking",
                    "url": f"https://example.com/{workflow_run_id}/002",
                    "content": "BYD cash flow quality still needs checking.",
                    "publish_time": "2026-05-12T11:00:00+00:00",
                    "source_quality_hint": 0.74,
                    "metadata": {"evidence_type": "company_news"},
                },
            ),
            completed_at="2026-05-13T09:30:00+00:00",
        ),
    )


def test_workflow_api_create_detail_snapshot_trace_and_events() -> None:
    client = TestClient(create_app())
    runtime = client.app.state.runtime
    runtime.agent_swarm.llm_provider = None
    runtime.judge.llm_provider = None
    runtime.workflow_service.acquisition = EvidenceAcquisitionService(
        search_pool=SearchAgentPool(
            providers={
                "tavily": MockSearchProvider(
                    items_by_source={
                        "tavily": (
                            {
                                "external_id": "api_news_001",
                                "title": "BYD margin improved",
                                "url": "https://example.com/api/001",
                                "content": "BYD reported margin improvement.",
                                "publish_time": "2026-05-12T10:00:00+00:00",
                                "source_quality_hint": 0.86,
                                "metadata": {"evidence_type": "company_news"},
                            },
                            {
                                "external_id": "api_news_002",
                                "title": "BYD cash flow needs checking",
                                "url": "https://example.com/api/002",
                                "content": "BYD cash flow quality still needs checking.",
                                "publish_time": "2026-05-12T11:00:00+00:00",
                                "source_quality_hint": 0.74,
                                "metadata": {"evidence_type": "company_news"},
                            },
                        )
                    }
                )
            },
            evidence_store=runtime.evidence_store,
        )
    )

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
    assert detail.json()["data"]["status"] == "completed"

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
    assert trace.json()["data"]["trace_nodes"]

    events = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/events")
    assert events.status_code == 200, events.text
    assert "event: workflow_queued" in events.text


def test_workflow_api_not_found_error() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/workflow-runs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKFLOW_RUN_NOT_FOUND"


def test_workflow_api_create_defaults_to_queued_without_autorun() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/workflow-runs",
        json={
            "ticker": "002594",
            "analysis_time": "2026-05-13T10:00:00+00:00",
            "workflow_config_id": "mvp_bull_judge_v1",
        },
    )

    assert response.status_code == 202, response.text
    created = response.json()["data"]
    assert created["status"] == "queued"

    detail = client.get(f"/api/v1/workflow-runs/{created['workflow_run_id']}")
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["status"] == "queued"
    assert data["stage"] == "queued"
    assert data["started_at"] is None


def test_workflow_api_snapshot_projects_judge_tool_calls_and_events() -> None:
    client = TestClient(create_app())
    runtime = client.app.state.runtime
    runtime.agent_swarm.llm_provider = None
    runtime.judge.llm_provider = None
    service = runtime.workflow_service

    queued = service.create_run(
        WorkflowRunCreate(
            ticker="002594",
            stock_code="002594.SZ",
            entity_id="ent_company_002594",
            analysis_time=_analysis_time(),
            workflow_config_id="mvp_bull_judge_v1",
            query=WorkflowQuery(sources=("tavily",), evidence_types=("company_news",)),
            options=WorkflowOptions(auto_run=False),
        )
    )
    _seed_workflow_evidence(queued.workflow_run_id, runtime.evidence_store)
    run = service.run_once(queued.workflow_run_id)

    snapshot = client.get(
        f"/api/v1/workflow-runs/{run.workflow_run_id}/snapshot",
        params={"include_events": True},
    )
    assert snapshot.status_code == 200, snapshot.text
    data = snapshot.json()["data"]
    assert len(data["judge_tool_calls"]) == 2
    tool_call = data["judge_tool_calls"][0]
    assert set(tool_call.keys()) == {
        "tool_call_id",
        "judgment_id",
        "tool_name",
        "input",
        "output_summary",
        "referenced_evidence_ids",
        "created_at",
    }
    assert tool_call["judgment_id"] == run.judgment_id
    assert tool_call["tool_name"] == "get_evidence_detail"
    assert "result_ref" not in tool_call

    event_types = [event["event_type"] for event in data["events"]]
    assert event_types.count("judge_tool_call_completed") == 2
    assert event_types.index("judge_tool_call_completed") < event_types.index("judgment_completed")
