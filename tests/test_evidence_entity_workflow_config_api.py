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


def test_evidence_detail_structure_raw_and_entity_evidence(client: TestClient) -> None:
    evidence = client.get("/api/v1/evidence/ev_000001")
    assert evidence.status_code == 200, evidence.text
    data = evidence.json()["data"]
    assert data["evidence_id"] == "ev_000001"
    assert data["raw_ref"] == "raw_000001"
    assert data["objective_summary"]
    assert data["links"]["raw"].endswith("/raw")

    structure = client.get("/api/v1/evidence/ev_000001/structure")
    assert structure.status_code == 200, structure.text
    assert structure.json()["data"]["evidence_structure_id"] == "struct_000001"

    raw = client.get("/api/v1/evidence/ev_000001/raw")
    assert raw.status_code == 200, raw.text
    assert raw.json()["data"]["raw_ref"] == "raw_000001"
    assert raw.json()["data"]["derived_evidence_ids"] == ["ev_000001"]

    by_entity = client.get("/api/v1/entities/ent_company_002594/evidence")
    assert by_entity.status_code == 200, by_entity.text
    assert by_entity.json()["data"][0]["evidence_id"] == "ev_000001"


def test_entities_and_relations_api(client: TestClient) -> None:
    listing = client.get("/api/v1/entities", params={"query": "BYD", "type": "company"})
    assert listing.status_code == 200, listing.text
    row = listing.json()["data"][0]
    assert row["entity_id"] == "ent_company_002594"
    assert row["entity_type"] == "company"

    detail = client.get("/api/v1/entities/ent_company_002594")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["name"] == "比亚迪"

    relations = client.get("/api/v1/entities/ent_company_002594/relations")
    assert relations.status_code == 200, relations.text
    assert relations.json()["data"][0]["relation_type"] == "belongs_to_industry"

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
