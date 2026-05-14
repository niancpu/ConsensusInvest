import unittest
from datetime import datetime, timezone

from consensusinvest import evidence_normalizer
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import (
    SearchResultItem,
    SearchResultPackage,
    SearchTarget,
)


class EvidenceNormalizerContractTests(unittest.TestCase):
    def make_envelope(self) -> InternalCallEnvelope:
        return InternalCallEnvelope(
            request_id="req_normalizer_001",
            correlation_id="corr_normalizer_001",
            workflow_run_id="wr_normalizer_001",
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key="normalize_search_result",
            trace_level="standard",
        )

    def make_package(self, *items) -> SearchResultPackage:
        return SearchResultPackage(
            task_id="st_normalizer_001",
            worker_id="worker_tavily",
            source="tavily",
            source_type="web_news",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("BYD",),
            ),
            items=items,
            completed_at="2026-05-13T09:00:00+00:00",
            metadata={"evidence_type": "company_news"},
        )

    def make_item(self, **overrides) -> SearchResultItem:
        data = {
            "external_id": "news_001",
            "title": "BYD factual operating update",
            "url": "https://example.com/news/001",
            "content": "BYD reported a factual operating update.",
            "content_preview": "BYD operating update.",
            "publish_time": "2026-05-12T10:00:00+00:00",
            "fetched_at": "2026-05-13T09:00:00+00:00",
            "author": "Example News",
            "language": "en",
            "source_quality_hint": 0.8,
            "metadata": {"quality_notes": ["source provided a short preview"]},
        }
        data.update(overrides)
        return SearchResultItem(**data)

    def normalize(self, *items):
        return evidence_normalizer.normalize_search_result_package(
            self.make_envelope(),
            self.make_package(*items),
        )

    def test_normalizes_search_result_into_raw_and_evidence_drafts(self):
        result = self.normalize(self.make_item())

        self.assertEqual("accepted", result.status)
        self.assertEqual(1, len(result.raw_items))
        self.assertEqual(1, len(result.evidence_items))

        raw = result.raw_items[0]
        evidence = result.evidence_items[0]

        self.assertEqual("tavily", raw.source)
        self.assertEqual("web_news", raw.source_type)
        self.assertEqual("002594", raw.ticker)
        self.assertEqual(("ent_company_002594",), raw.entity_ids)
        self.assertEqual("https://example.com/news/001", raw.url)
        self.assertEqual("BYD factual operating update", raw.title)
        self.assertEqual("BYD operating update.", raw.content_preview)
        self.assertEqual("Example News", raw.author)
        self.assertEqual("en", raw.language)
        self.assertEqual("st_normalizer_001", raw.ingest_context["task_id"])

        self.assertEqual(raw.raw_ref, evidence.raw_ref)
        self.assertEqual("company_news", evidence.evidence_type)
        self.assertEqual("BYD reported a factual operating update.", evidence.content)
        self.assertEqual(0.8, evidence.source_quality)
        self.assertIsNotNone(evidence.freshness)
        self.assertGreaterEqual(evidence.freshness, 0.0)
        self.assertLessEqual(evidence.freshness, 1.0)
        self.assertIn("source provided a short preview", evidence.quality_notes)

    def test_rejects_item_published_after_analysis_time(self):
        result = self.normalize(
            self.make_item(
                external_id="news_future",
                url="https://example.com/news/future",
                publish_time="2026-05-14T10:00:00+00:00",
            )
        )

        self.assertEqual("rejected", result.status)
        self.assertEqual([], result.raw_items)
        self.assertEqual([], result.evidence_items)
        self.assertEqual("publish_time_after_analysis_time", result.rejected_items[0].reason)

    def test_rejects_item_without_url_or_external_id(self):
        result = self.normalize(self.make_item(external_id=None, url=None))

        self.assertEqual("rejected", result.status)
        self.assertEqual("invalid_request", result.rejected_items[0].reason)

    def test_rejects_directional_fields(self):
        result = self.normalize(
            {
                "external_id": "news_directional",
                "title": "Directional item",
                "url": "https://example.com/news/directional",
                "content": "Provider added a directional field.",
                "publish_time": "2026-05-12T10:00:00+00:00",
                "bullish": True,
            }
        )

        self.assertEqual("rejected", result.status)
        self.assertEqual("write_boundary_violation", result.rejected_items[0].reason)
        self.assertIn("bullish", result.rejected_items[0].message)

    def test_does_not_pass_directional_fields_into_drafts(self):
        result = self.normalize(
            self.make_item(
                raw_payload={
                    "provider_response": {
                        "bullish": True,
                        "recommendation": "buy",
                    }
                }
            )
        )

        self.assertEqual("accepted", result.status)
        raw = result.raw_items[0]
        evidence = result.evidence_items[0]

        self.assertFalse(hasattr(raw, "bullish"))
        self.assertFalse(hasattr(raw, "recommendation"))
        self.assertFalse(hasattr(evidence, "bullish"))
        self.assertFalse(hasattr(evidence, "recommendation"))


if __name__ == "__main__":
    unittest.main()
