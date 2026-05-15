import unittest
from datetime import datetime, timezone

from consensusinvest.evidence_store import (
    EvidenceReferenceBatch,
    EvidenceReferenceQuery,
    EvidenceStructureDraft,
    FakeEvidenceStoreClient,
    MarketSnapshotDraft,
    MarketSnapshotQuery,
)
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import (
    SearchResultPackage,
    SearchTarget,
)


class EvidenceStoreContractTests(unittest.TestCase):
    def make_envelope(self, *, idempotency_key="evidence_contract") -> InternalCallEnvelope:
        return InternalCallEnvelope(
            request_id="req_evidence_001",
            correlation_id="corr_evidence_001",
            workflow_run_id=None,
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key=idempotency_key,
            trace_level="standard",
        )

    def make_package(self, *items, source="tavily") -> SearchResultPackage:
        return SearchResultPackage(
            task_id="st_contract_001",
            worker_id="worker_tavily",
            source=source,
            source_type="web_news",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("BYD",),
            ),
            items=tuple(items),
            completed_at="2026-05-13T09:00:00+00:00",
            metadata={"evidence_type": "company_news"},
        )

    def make_item(self, **overrides):
        item = {
            "external_id": "news_001",
            "title": "BYD result",
            "url": "https://example.com/news/001",
            "content": "BYD published a factual operating update.",
            "content_preview": "BYD operating update.",
            "publish_time": "2026-05-12T10:00:00+00:00",
            "fetched_at": "2026-05-13T09:00:00+00:00",
            "author": "Example News",
            "language": "en",
            "source_quality_hint": 0.8,
            "relevance": 0.9,
            "raw_payload": {"provider_response": {"id": "news_001"}},
        }
        item.update(overrides)
        return item

    def test_ingest_creates_raw_and_evidence_and_allows_detail_lookup(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()

        result = store.ingest_search_result(envelope, self.make_package(self.make_item()))

        self.assertEqual("accepted", result.status)
        self.assertEqual(["raw_000001"], result.accepted_raw_refs)
        self.assertEqual(["ev_000001"], result.created_evidence_ids)

        raw = store.get_raw(envelope, "raw_000001")
        self.assertEqual("raw_000001", raw.raw_ref)
        self.assertEqual("https://example.com/news/001", raw.url)
        self.assertEqual("002594", raw.ticker)
        self.assertIn("ent_company_002594", raw.entity_ids)

        detail = store.get_evidence(envelope, "ev_000001")
        self.assertEqual("ev_000001", detail.evidence.evidence_id)
        self.assertEqual("raw_000001", detail.raw_ref)
        self.assertEqual("company_news", detail.evidence.evidence_type)
        self.assertIsNone(detail.structure)

    def test_ingest_rejects_duplicate_url_and_duplicate_content_not_only_title(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        first = self.make_item(title="Same title")
        duplicate_url = self.make_item(
            external_id="news_002",
            title="Different title",
            url="https://example.com/news/001",
            content="Different content.",
        )
        duplicate_content = self.make_item(
            external_id="news_003",
            title="Another title",
            url="https://example.com/news/003",
            content="BYD published a factual operating update.",
        )

        first_result = store.ingest_search_result(envelope, self.make_package(first))
        second_result = store.ingest_search_result(
            envelope,
            self.make_package(duplicate_url, duplicate_content),
        )

        self.assertEqual("accepted", first_result.status)
        self.assertEqual("rejected", second_result.status)
        self.assertEqual(
            ["duplicate_request", "duplicate_request"],
            [item.reason for item in second_result.rejected_items],
        )

    def test_duplicate_ingest_links_existing_evidence_to_new_workflow(self):
        store = FakeEvidenceStoreClient()
        first_envelope = self.make_envelope(idempotency_key="workflow_1")
        second_envelope = InternalCallEnvelope(
            request_id="req_evidence_002",
            correlation_id="corr_evidence_002",
            workflow_run_id="wr_second",
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key="workflow_2",
            trace_level="standard",
        )

        first_result = store.ingest_search_result(first_envelope, self.make_package(self.make_item()))
        second_result = store.ingest_search_result(second_envelope, self.make_package(self.make_item()))
        page = store.query_evidence(
            second_envelope,
            {
                "workflow_run_id": "wr_second",
                "ticker": "002594",
                "entity_ids": ["ent_company_002594"],
                "evidence_types": ["company_news"],
            },
        )

        self.assertEqual(["ev_000001"], first_result.created_evidence_ids)
        self.assertEqual("partial_accepted", second_result.status)
        self.assertEqual(["ev_000001"], second_result.updated_evidence_ids)
        self.assertEqual(1, page.total)
        self.assertEqual("ev_000001", page.items[0].evidence_id)

    def test_ingest_rejects_item_published_after_analysis_time(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        future_item = self.make_item(publish_time="2026-05-14T10:00:00+00:00")

        result = store.ingest_search_result(envelope, self.make_package(future_item))

        self.assertEqual("rejected", result.status)
        self.assertEqual("publish_time_after_analysis_time", result.rejected_items[0].reason)
        self.assertEqual([], result.created_evidence_ids)

    def test_ingest_rejects_directional_fields_in_evidence_items(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        directional = self.make_item(bullish=True)

        result = store.ingest_search_result(envelope, self.make_package(directional))

        self.assertEqual("rejected", result.status)
        self.assertEqual("write_boundary_violation", result.rejected_items[0].reason)

    def test_query_evidence_filters_and_paginates(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        items = [
            self.make_item(
                external_id="news_001",
                url="https://example.com/news/001",
                source_quality_hint=0.9,
                publish_time="2026-05-12T10:00:00+00:00",
                metadata={"evidence_type": "company_news"},
            ),
            self.make_item(
                external_id="news_002",
                url="https://example.com/news/002",
                source_quality_hint=0.5,
                publish_time="2026-05-11T10:00:00+00:00",
                metadata={"evidence_type": "company_news"},
                content="Second distinct fact.",
            ),
            self.make_item(
                external_id="news_003",
                url="https://example.com/news/003",
                source_quality_hint=0.95,
                publish_time="2026-05-10T10:00:00+00:00",
                metadata={"evidence_type": "financial_report"},
                content="Third distinct fact.",
            ),
        ]
        store.ingest_search_result(envelope, self.make_package(*items))

        page = store.query_evidence(
            envelope,
            {
                "ticker": "002594",
                "entity_ids": ["ent_company_002594"],
                "evidence_types": ["company_news"],
                "source_quality_min": 0.8,
                "publish_time_lte": "2026-05-13T10:00:00+00:00",
                "limit": 1,
                "offset": 0,
            },
        )

        self.assertEqual(1, page.total)
        self.assertEqual(1, len(page.items))
        self.assertEqual("ev_000001", page.items[0].evidence_id)

    def test_query_evidence_filters_by_entity_index(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        items = [
            self.make_item(
                external_id="news_001",
                url="https://example.com/news/001",
                entity_ids=["ent_company_002594", "ent_industry_ev"],
            ),
            self.make_item(
                external_id="news_002",
                url="https://example.com/news/002",
                content="Second distinct fact.",
                entity_ids=["ent_company_000001"],
            ),
        ]
        store.ingest_search_result(envelope, self.make_package(*items))

        page = store.query_evidence(
            envelope,
            {
                "entity_ids": ["ent_industry_ev"],
                "limit": 10,
                "offset": 0,
            },
        )

        self.assertEqual(1, page.total)
        self.assertEqual("ev_000001", page.items[0].evidence_id)
        self.assertEqual(
            ("ent_company_002594", "ent_industry_ev"),
            page.items[0].entity_ids,
        )

    def test_save_structure_versions_and_get_evidence_returns_latest(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        store.ingest_search_result(envelope, self.make_package(self.make_item()))

        first = store.save_structure(
            envelope,
            EvidenceStructureDraft(
                evidence_id="ev_000001",
                objective_summary="First objective summary.",
                claims=[{"claim": "Reported fact.", "evidence_span": "fact"}],
                created_by_agent_id="structurer_v1",
            ),
        )
        second = store.save_structure(
            envelope,
            EvidenceStructureDraft(
                evidence_id="ev_000001",
                objective_summary="Second objective summary.",
                created_by_agent_id="structurer_v1",
            ),
        )

        detail = store.get_evidence(envelope, "ev_000001")

        self.assertEqual(1, first.version)
        self.assertEqual(2, second.version)
        self.assertEqual("Second objective summary.", detail.structure.objective_summary)

    def test_report_view_can_only_save_cited_references(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        store.ingest_search_result(envelope, self.make_package(self.make_item()))

        result = store.save_references(
            envelope,
            EvidenceReferenceBatch(
                source_type="report_view",
                source_id="report_view_001",
                references=[
                    {"evidence_id": "ev_000001", "reference_role": "supports"},
                    {"evidence_id": "ev_000001", "reference_role": "cited"},
                ],
            ),
        )
        references = store.query_references(
            envelope,
            EvidenceReferenceQuery(source_type="report_view"),
        )

        self.assertEqual(1, len(result.accepted_references))
        self.assertEqual(1, len(result.rejected_references))
        self.assertEqual("write_boundary_violation", result.rejected_references[0].reason)
        self.assertEqual("cited", references[0].reference_role)

    def test_market_snapshot_save_query_and_get(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        older = store.save_market_snapshot(
            envelope,
            MarketSnapshotDraft(
                snapshot_type="stock_quote",
                ticker="002594",
                entity_ids=("ent_company_002594",),
                source="akshare",
                snapshot_time="2026-05-12T10:00:00+00:00",
                fetched_at="2026-05-12T10:00:01+00:00",
                metrics={"price": 200.0, "change_rate": 1.2},
            ),
        )
        store.save_market_snapshot(
            envelope,
            MarketSnapshotDraft(
                snapshot_type="stock_quote",
                ticker="002594",
                entity_ids=("ent_company_002594",),
                source="akshare",
                snapshot_time="2026-05-13T09:30:00+00:00",
                metrics={"price": 201.0},
            ),
        )

        page = store.query_market_snapshots(
            envelope,
            MarketSnapshotQuery(
                ticker="002594",
                entity_ids=("ent_company_002594",),
                snapshot_types=("stock_quote",),
                snapshot_time_lte="2026-05-12T23:59:00+00:00",
            ),
        )
        loaded = store.get_market_snapshot(envelope, older.market_snapshot_id)

        self.assertEqual(1, page.total)
        self.assertEqual(older.market_snapshot_id, page.items[0].market_snapshot_id)
        self.assertEqual({"price": 200.0, "change_rate": 1.2}, loaded.metrics)

    def test_market_snapshot_rejects_directional_fields(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()

        with self.assertRaises(ValueError) as context:
            store.save_market_snapshot(
                envelope,
                {
                    "snapshot_type": "stock_quote",
                    "ticker": "002594",
                    "snapshot_time": "2026-05-12T10:00:00+00:00",
                    "metrics": {"price": 200.0, "recommendation": "buy"},
                },
            )

        self.assertIn("write_boundary_violation", str(context.exception))

    def test_market_snapshot_rejects_snapshot_time_after_analysis_time(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()

        with self.assertRaises(ValueError) as context:
            store.save_market_snapshot(
                envelope,
                MarketSnapshotDraft(
                    snapshot_type="stock_quote",
                    ticker="002594",
                    snapshot_time="2026-05-14T10:00:00+00:00",
                    metrics={"price": 210.0},
                ),
            )

        message = str(context.exception)
        self.assertIn("snapshot_time", message)
        self.assertIn("analysis_time", message)

    def test_market_snapshot_query_defaults_to_analysis_time_boundary(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope()
        store.save_market_snapshot(
            envelope,
            MarketSnapshotDraft(
                snapshot_type="stock_quote",
                ticker="002594",
                snapshot_time="2026-05-12T10:00:00+00:00",
                metrics={"price": 200.0},
            ),
        )
        store.save_market_snapshot(
            envelope,
            MarketSnapshotDraft(
                snapshot_type="stock_quote",
                ticker="002594",
                snapshot_time="2026-05-13T09:30:00+00:00",
                metrics={"price": 201.0},
            ),
        )

        page = store.query_market_snapshots(
            envelope,
            MarketSnapshotQuery(ticker="002594", snapshot_types=("stock_quote",)),
        )

        self.assertEqual(2, page.total)
        self.assertEqual(201.0, page.items[0].metrics["price"])


if __name__ == "__main__":
    unittest.main()
