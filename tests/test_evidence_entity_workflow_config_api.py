from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from consensusinvest.app import create_app
from consensusinvest.evidence_store import EvidenceReferenceBatch
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_default_runtime_has_no_seeded_evidence_or_entities(client: TestClient) -> None:
    evidence = client.get("/api/v1/evidence/ev_000001")
    assert evidence.status_code == 404
    assert evidence.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"

    by_entity = client.get("/api/v1/entities/ent_company_002594/evidence")
    assert by_entity.status_code == 404
    assert by_entity.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_entities_and_relations_api(client: TestClient) -> None:
    listing = client.get("/api/v1/entities", params={"query": "BYD", "type": "company"})
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"] == []

    detail = client.get("/api/v1/entities/ent_company_002594")
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    relations = client.get("/api/v1/entities/ent_company_002594/relations")
    assert relations.status_code == 404
    assert relations.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    missing = client.get("/api/v1/entities/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_workflow_configs_api(client: TestClient) -> None:
    response = client.get("/api/v1/workflow-configs")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data[0]["workflow_config_id"] == "mvp_bull_judge_v1"
    assert data[0]["agents"][0]["agent_id"] == "bull_v1"


def test_workflow_evidence_api_reads_same_runtime_store(client: TestClient) -> None:
    created = client.post(
        "/api/v1/workflow-runs",
        json={
            "ticker": "002594",
            "analysis_time": "2026-05-13T10:00:00+00:00",
            "workflow_config_id": "mvp_bull_judge_v1",
            "query": {"sources": ["tavily"], "evidence_types": ["company_news"]},
            "options": {"auto_run": False},
        },
    )
    assert created.status_code == 202, created.text
    workflow_run_id = created.json()["data"]["workflow_run_id"]

    evidence_store = client.app.state.runtime.evidence_store
    envelope = InternalCallEnvelope(
        request_id="req_test_runtime_shared",
        correlation_id="corr_test_runtime_shared",
        workflow_run_id=workflow_run_id,
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="test",
        idempotency_key=f"seed_{workflow_run_id}",
    )
    result = evidence_store.ingest_search_result(
        envelope,
        SearchResultPackage(
            task_id="st_test_runtime_shared",
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
                    "title": "Workflow scoped BYD evidence",
                    "url": f"https://example.com/{workflow_run_id}/001",
                    "content": "Workflow scoped factual evidence.",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "source_quality_hint": 0.86,
                    "relevance": 0.9,
                },
            ),
            completed_at="2026-05-13T09:30:00+00:00",
            metadata={"evidence_type": "company_news"},
        ),
    )
    evidence_id = result.created_evidence_ids[0]
    raw_ref = result.accepted_raw_refs[0]
    evidence_store.save_references(
        envelope,
        EvidenceReferenceBatch(
            source_type="agent_argument",
            source_id="arg_test_runtime_shared",
            references=[{"evidence_id": evidence_id, "reference_role": "supports", "round": 1}],
        ),
    )

    evidence = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["data"][0]["evidence_id"] == evidence_id

    raw_items = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/raw-items")
    assert raw_items.status_code == 200, raw_items.text
    assert raw_items.json()["data"][0]["raw_ref"] == raw_ref

    references = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/evidence-references")
    assert references.status_code == 200, references.text
    assert references.json()["data"][0]["evidence_id"] == evidence_id


def test_workflow_evidence_api_projects_reused_evidence_to_current_workflow(client: TestClient) -> None:
    first = client.post(
        "/api/v1/workflow-runs",
        json={
            "ticker": "002594",
            "analysis_time": "2026-05-13T10:00:00+00:00",
            "workflow_config_id": "mvp_bull_judge_v1",
            "query": {"sources": ["tavily"], "evidence_types": ["company_news"]},
            "options": {"auto_run": False},
        },
    )
    second = client.post(
        "/api/v1/workflow-runs",
        json={
            "ticker": "002594",
            "analysis_time": "2026-05-13T10:00:00+00:00",
            "workflow_config_id": "mvp_bull_judge_v1",
            "query": {"sources": ["tavily"], "evidence_types": ["company_news"]},
            "options": {"auto_run": False},
        },
    )
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    first_workflow_id = first.json()["data"]["workflow_run_id"]
    second_workflow_id = second.json()["data"]["workflow_run_id"]

    evidence_store = client.app.state.runtime.evidence_store
    first_envelope = InternalCallEnvelope(
        request_id="req_test_reuse_first",
        correlation_id="corr_test_reuse_first",
        workflow_run_id=first_workflow_id,
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="test",
        idempotency_key=f"seed_{first_workflow_id}",
    )
    second_envelope = InternalCallEnvelope(
        request_id="req_test_reuse_second",
        correlation_id="corr_test_reuse_second",
        workflow_run_id=second_workflow_id,
        analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        requested_by="test",
        idempotency_key=f"seed_{second_workflow_id}",
    )
    package = SearchResultPackage(
        task_id="st_test_reuse",
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
                "external_id": "shared_news_001",
                "title": "Shared workflow BYD evidence",
                "url": "https://example.com/shared/001",
                "content": "Shared factual evidence.",
                "publish_time": "2026-05-12T10:00:00+00:00",
                "source_quality_hint": 0.86,
                "relevance": 0.9,
            },
        ),
        completed_at="2026-05-13T09:30:00+00:00",
        metadata={"evidence_type": "company_news"},
    )

    first_result = evidence_store.ingest_search_result(first_envelope, package)
    second_result = evidence_store.ingest_search_result(second_envelope, package)

    assert first_result.created_evidence_ids == ["ev_000001"]
    assert second_result.updated_evidence_ids == ["ev_000001"]

    evidence = client.get(f"/api/v1/workflow-runs/{second_workflow_id}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["data"][0]["evidence_id"] == "ev_000001"
    assert evidence.json()["data"][0]["workflow_run_id"] == second_workflow_id

    raw_items = client.get(f"/api/v1/workflow-runs/{second_workflow_id}/raw-items")
    assert raw_items.status_code == 200, raw_items.text
    assert raw_items.json()["data"][0]["raw_ref"] == "raw_000001"
    assert raw_items.json()["data"][0]["workflow_run_id"] == second_workflow_id
