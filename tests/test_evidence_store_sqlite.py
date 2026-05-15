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

    def test_ingest_writes_evidence_entities_and_reopen_queries_by_entity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "evidence.db"
            store = self.make_store(db_path)
            envelope = self.make_envelope()
            item = self.make_item(
                entity_ids=[
                    "ent_company_002594",
                    "ent_industry_ev",
                    "ent_industry_ev",
                ],
            )

            result = store.ingest_search_result(envelope, self.make_package(item))

            self.assertEqual("accepted", result.status)
            table = store._conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'evidence_entities'
                """
            ).fetchone()
            rows = store._conn.execute(
                """
                SELECT evidence_id, entity_id
                FROM evidence_entities
                ORDER BY entity_id
                """
            ).fetchall()
            duplicate_insert = store._conn.execute(
                """
                INSERT OR IGNORE INTO evidence_entities (evidence_id, entity_id)
                VALUES (?, ?)
                """,
                ("ev_000001", "ent_industry_ev"),
            )

            self.assertIsNotNone(table)
            self.assertEqual(2, len(rows))
            self.assertEqual(0, duplicate_insert.rowcount)
            self.assertEqual(
                {
                    ("ev_000001", "ent_company_002594"),
                    ("ev_000001", "ent_industry_ev"),
                },
                {(row["evidence_id"], row["entity_id"]) for row in rows},
            )

            store.close()
            reopened = self.make_store(db_path)
            page = reopened.query_evidence(
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

    def test_duplicate_ingest_links_existing_evidence_to_new_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "evidence.db"
            store = self.make_store(db_path)
            first_envelope = self.make_envelope(idempotency_key="workflow_1")
            second_envelope = InternalCallEnvelope(
                request_id="req_sqlite_002",
                correlation_id="corr_sqlite_002",
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
            store.close()

            reopened = self.make_store(db_path)
            reopened_page = reopened.query_evidence(
                second_envelope,
                {"workflow_run_id": "wr_second", "limit": 10},
            )

            self.assertEqual(1, reopened_page.total)
            self.assertEqual("ev_000001", reopened_page.items[0].evidence_id)
            reopened.close()

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
                    snapshot_time="2026-05-13T09:30:00+00:00",
                    metrics={"price": 201.0},
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

            self.assertEqual(2, default_page.total)
            self.assertEqual(201.0, default_page.items[0].metrics["price"])
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

    def test_market_snapshot_rejects_snapshot_time_after_analysis_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir) / "evidence.db")
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
            page = store.query_market_snapshots(
                envelope,
                MarketSnapshotQuery(ticker="002594", snapshot_types=("stock_quote",)),
            )
            self.assertEqual(0, page.total)
            store.close()


if __name__ == "__main__":
    unittest.main()
