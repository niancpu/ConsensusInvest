import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from consensusinvest.evidence_store import (
    EvidenceReferenceBatch,
    EvidenceReferenceQuery,
    EvidenceStructureDraft,
    MarketSnapshotDraft,
    MarketSnapshotQuery,
    SQLiteEvidenceStoreClient,
)
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget


class SQLiteEvidenceStoreTests(unittest.TestCase):
    def make_envelope(self, *, idempotency_key="sqlite_evidence") -> InternalCallEnvelope:
        return InternalCallEnvelope(
            request_id="req_sqlite_001",
            correlation_id="corr_sqlite_001",
            workflow_run_id=None,
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key=idempotency_key,
            trace_level="standard",
        )

    def make_package(self, *items, source="tavily") -> SearchResultPackage:
        return SearchResultPackage(
            task_id="st_sqlite_001",
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

    def make_store(self, db_path: Path) -> SQLiteEvidenceStoreClient:
        self.addCleanup(lambda: None)
        return SQLiteEvidenceStoreClient(db_path)

    def test_ingest_get_query_and_reopen_same_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "evidence.db"
            store = self.make_store(db_path)
            envelope = self.make_envelope()

            result = store.ingest_search_result(envelope, self.make_package(self.make_item()))

            self.assertEqual("accepted", result.status)
            self.assertEqual(["raw_000001"], result.accepted_raw_refs)
            self.assertEqual(["ev_000001"], result.created_evidence_ids)
            self.assertEqual("002594", store.get_raw(envelope, "raw_000001").ticker)

            page = store.query_evidence(
                envelope,
                {
                    "ticker": "002594",
                    "entity_ids": ["ent_company_002594"],
                    "evidence_types": ["company_news"],
                    "source_quality_min": 0.7,
                },
            )
            self.assertEqual(1, page.total)
            self.assertEqual("ev_000001", page.items[0].evidence_id)

            store.close()
            reopened = self.make_store(db_path)
            detail = reopened.get_evidence(envelope, "ev_000001")
            raw = reopened.get_raw(envelope, "raw_000001")

            self.assertEqual("ev_000001", detail.evidence.evidence_id)
            self.assertEqual("https://example.com/news/001", raw.url)
            reopened.close()

    def test_rejects_duplicate_url_external_id_and_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
            envelope = self.make_envelope()
            store.ingest_search_result(envelope, self.make_package(self.make_item()))

            duplicate_url = self.make_item(
                external_id="news_002",
                title="Different title",
                url="https://example.com/news/001",
                content="Different content.",
            )
            duplicate_external_id = self.make_item(
                external_id="news_001",
                url=None,
                content="A separate fact with same external id.",
            )
            duplicate_content = self.make_item(
                external_id="news_003",
                title="Another title",
                url="https://example.com/news/003",
                content="BYD published a factual operating update.",
            )

            by_url = store.ingest_search_result(envelope, self.make_package(duplicate_url))
            by_external_id = store.ingest_search_result(
                envelope,
                self.make_package(duplicate_external_id),
            )
            by_content = store.ingest_search_result(envelope, self.make_package(duplicate_content))

            self.assertEqual("duplicate_request", by_url.rejected_items[0].reason)
            self.assertEqual("duplicate_request", by_external_id.rejected_items[0].reason)
            self.assertEqual("duplicate_request", by_content.rejected_items[0].reason)
            store.close()

    def test_rejects_publish_time_after_analysis_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
            result = store.ingest_search_result(
                self.make_envelope(),
                self.make_package(self.make_item(publish_time="2026-05-14T10:00:00+00:00")),
            )

            self.assertEqual("rejected", result.status)
            self.assertEqual("publish_time_after_analysis_time", result.rejected_items[0].reason)
            store.close()

    def test_ingest_requires_url_or_external_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
            item = self.make_item(external_id=None, url=None)

            result = store.ingest_search_result(
                self.make_envelope(),
                self.make_package(item),
            )

            self.assertEqual("rejected", result.status)
            self.assertEqual("invalid_request", result.rejected_items[0].reason)
            store.close()

    def test_structure_versions_and_latest_detail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
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
            store.close()

    def test_report_view_can_only_save_cited_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
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
            store.close()

    def test_market_snapshot_query_boundary_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
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
                    snapshot_time="2026-05-14T10:00:00+00:00",
                    metrics={"price": 210.0},
                ),
            )

            default_page = store.query_market_snapshots(
                envelope,
                MarketSnapshotQuery(ticker="002594", snapshot_types=("stock_quote",)),
            )
            explicit_page = store.query_market_snapshots(
                envelope,
                MarketSnapshotQuery(
                    ticker="002594",
                    snapshot_types=("stock_quote",),
                    snapshot_time_lte="2026-05-12T23:59:00+00:00",
                ),
            )
            loaded = store.get_market_snapshot(envelope, older.market_snapshot_id)

            self.assertEqual(1, default_page.total)
            self.assertEqual(1, explicit_page.total)
            self.assertEqual(older.market_snapshot_id, explicit_page.items[0].market_snapshot_id)
            self.assertEqual({"price": 200.0, "change_rate": 1.2}, loaded.metrics)
            with self.assertRaises(ValueError):
                store.query_market_snapshots(
                    envelope,
                    MarketSnapshotQuery(
                        ticker="002594",
                        snapshot_time_lte="2026-05-14T10:00:00+00:00",
                    ),
                )
            store.close()


if __name__ == "__main__":
    unittest.main()
