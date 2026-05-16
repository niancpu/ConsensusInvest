import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone

from consensusinvest import evidence_structuring
from consensusinvest.evidence_store import (
    EvidenceDetail,
    EvidenceItem,
    EvidenceStructure,
    RawItem,
)
from consensusinvest.runtime import InternalCallEnvelope


class RecordingEvidenceStore:
    def __init__(self, *, existing_structure=None) -> None:
        self.raw = RawItem(
            raw_ref="raw_000001",
            source="tavily",
            source_type="web_news",
            ticker="002594",
            entity_ids=("ent_company_002594",),
            title="BYD factual operating update",
            content="BYD reported a factual operating update.",
            content_preview="BYD operating update.",
            url="https://example.com/news/001",
            publish_time=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
            fetched_at=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
        )
        self.evidence = EvidenceItem(
            evidence_id="ev_000001",
            raw_ref="raw_000001",
            ticker="002594",
            entity_ids=("ent_company_002594",),
            source="tavily",
            source_type="web_news",
            evidence_type="company_news",
            title="BYD factual operating update",
            content="BYD reported a factual operating update.",
            url="https://example.com/news/001",
            publish_time=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
            fetched_at=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
            source_quality=0.8,
            relevance=0.9,
            freshness=0.99,
            quality_notes=("normalized from search result",),
        )
        self.structure = existing_structure
        self.saved_structures = []

    def get_evidence(self, envelope, evidence_id):
        self.requested_evidence_id = evidence_id
        return EvidenceDetail(
            evidence=self.evidence,
            structure=self.structure,
            raw_ref=self.evidence.raw_ref,
        )

    def get_raw(self, envelope, raw_ref):
        self.requested_raw_ref = raw_ref
        return self.raw

    def save_structure(self, envelope, draft):
        self.saved_structures.append(draft)
        saved = EvidenceStructure(
            structure_id="struct_000001",
            evidence_id=draft.evidence_id,
            version=1,
            objective_summary=draft.objective_summary,
            key_facts=list(draft.key_facts),
            claims=list(draft.claims),
            structuring_confidence=draft.structuring_confidence,
            quality_notes=tuple(draft.quality_notes),
            created_by_agent_id=draft.created_by_agent_id,
            created_at=envelope.analysis_time,
        )
        self.structure = saved
        return saved


class EvidenceStructuringAgentContractTests(unittest.TestCase):
    def make_envelope(self) -> InternalCallEnvelope:
        return InternalCallEnvelope(
            request_id="req_structuring_001",
            correlation_id="corr_structuring_001",
            workflow_run_id="wr_structuring_001",
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key="structure_evidence",
            trace_level="standard",
        )

    def make_agent(self, store):
        return evidence_structuring.EvidenceStructuringAgent(
            evidence_store=store,
            agent_id="evidence_structurer_v1",
        )

    def test_generates_objective_summary_claims_and_saves_structure(self):
        store = RecordingEvidenceStore()
        agent = self.make_agent(store)

        result = agent.structure_evidence(self.make_envelope(), "ev_000001")

        self.assertEqual("structured", result.status)
        self.assertEqual("ev_000001", store.requested_evidence_id)
        self.assertEqual("raw_000001", store.requested_raw_ref)
        self.assertEqual(1, len(store.saved_structures))

        draft = store.saved_structures[0]
        self.assertEqual("ev_000001", draft.evidence_id)
        self.assertIn("BYD", draft.objective_summary)
        self.assertGreaterEqual(len(draft.claims), 1)
        self.assertIn("claim", draft.claims[0])
        self.assertIn("evidence_span", draft.claims[0])
        self.assertEqual("evidence_structurer_v1", draft.created_by_agent_id)
        self.assertIs(result.structure, store.structure)

    def test_skips_when_structure_already_exists(self):
        existing = EvidenceStructure(
            structure_id="struct_existing",
            evidence_id="ev_000001",
            version=1,
            objective_summary="Existing objective summary.",
            claims=[{"claim": "Existing claim.", "evidence_span": "Existing"}],
            created_by_agent_id="evidence_structurer_v1",
        )
        store = RecordingEvidenceStore(existing_structure=existing)
        agent = self.make_agent(store)

        result = agent.structure_evidence(self.make_envelope(), "ev_000001")

        self.assertEqual("skipped", result.status)
        self.assertEqual("structure_already_exists", result.reason)
        self.assertEqual([], store.saved_structures)
        self.assertIs(existing, result.structure)

    def test_rebuilds_existing_numeric_structure_from_raw_payload(self):
        existing = EvidenceStructure(
            structure_id="struct_existing",
            evidence_id="ev_000001",
            version=1,
            objective_summary="13.33 606.70 7280.40 11 12.00 -9.98 301042",
            claims=[{"claim": "13.33 606.70 7280.40", "evidence_span": "13.33"}],
            created_by_agent_id="evidence_structurer_v1",
        )
        store = RecordingEvidenceStore(existing_structure=existing)
        store.raw = replace(
            store.raw,
            source="akshare",
            source_type="market_data",
            raw_payload={
                "provider_response": {
                    "报告期": "2026-03-31",
                    "净利润": 606.70,
                    "营业收入": 7280.40,
                    "资产负债率": 72.20,
                    "_provider_api": "stock_financial_abstract",
                },
                "provider_api": "stock_financial_abstract",
                "provider_symbol": "002594",
            },
        )
        store.evidence = replace(
            store.evidence,
            source="akshare",
            source_type="market_data",
            content="13.33 606.70 7280.40 11 12.00 -9.98 301042",
        )
        agent = self.make_agent(store)

        result = agent.structure_evidence(self.make_envelope(), "ev_000001")

        self.assertEqual("structured", result.status)
        self.assertEqual(1, len(store.saved_structures))
        draft = store.saved_structures[0]
        self.assertIn("AkShare 结构化行情/财务数据", draft.objective_summary)
        self.assertIn("净利润：606.7", draft.objective_summary)
        self.assertIn("营业收入：7280.4", draft.objective_summary)

    def test_does_not_pass_directional_fields_into_structure(self):
        store = RecordingEvidenceStore()
        store.raw = replace(
            store.raw,
            raw_payload={
                "provider_response": {
                    "bullish": True,
                    "recommendation": "buy",
                }
            },
        )
        agent = self.make_agent(store)

        result = agent.structure_evidence(self.make_envelope(), "ev_000001")

        self.assertEqual("structured", result.status)
        draft = store.saved_structures[0]
        self.assertFalse(hasattr(draft, "bullish"))
        self.assertFalse(hasattr(draft, "bearish"))
        self.assertFalse(hasattr(draft, "recommendation"))
        draft_payload = asdict(draft)
        self.assertNotIn("bullish", str(draft_payload).lower())
        self.assertNotIn("recommendation", str(draft_payload).lower())


if __name__ == "__main__":
    unittest.main()
