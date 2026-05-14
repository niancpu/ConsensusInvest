import unittest
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchTask
from consensusinvest.search_agent.pool import SearchAgentPool


def _get_value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _status_name(value):
    value = _get_value(value, "value", value)
    return str(value)


class MarketSnapshotProvider:
    def __init__(self, source, items):
        self.source = source
        self.items = items

    def search(self, envelope, task):
        return {
            "worker_id": f"worker_{self.source}",
            "source_type": "market_data",
            "items": list(self.items),
            "completed_at": "2026-05-13T09:30:02+00:00",
        }

    def expand(self, envelope, task, action, seed_item=None):
        return {"items": []}


class RecordingMarketSnapshotStore:
    def __init__(self):
        self.saved_snapshots = []
        self.ingest_calls = []

    def ingest_search_result(self, envelope, package):
        self.ingest_calls.append((envelope, package))
        return {"created_evidence_ids": ["unexpected"]}

    def save_market_snapshot(self, envelope, snapshot):
        violation_path = _find_forbidden_key(snapshot)
        if violation_path is not None:
            raise ValueError(
                f"write_boundary_violation: directional field is not allowed in MarketSnapshot: {violation_path}"
            )
        self.saved_snapshots.append(snapshot)
        return {"market_snapshot_id": f"mkt_snap_{len(self.saved_snapshots):06d}"}


class MarketSnapshotSearchIngestTests(unittest.TestCase):
    def make_envelope(self):
        return InternalCallEnvelope(
            request_id="req_market_snapshot_search",
            correlation_id="corr_market_snapshot_search",
            workflow_run_id=None,
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="report_module",
            idempotency_key="market_snapshot_search",
            trace_level="standard",
        )

    def make_task(self, *, source="akshare"):
        return SearchTask(
            task_type="market_snapshot",
            target={
                "ticker": "002594",
                "stock_code": "002594.SZ",
                "entity_id": "ent_company_002594",
            },
            scope={
                "sources": [source],
                "evidence_types": ["stock_quote"],
                "max_results": 10,
            },
            constraints={"budget": {"max_provider_calls": 1}},
            callback={"ingest_target": "evidence_store", "workflow_run_id": None},
            idempotency_key="market_snapshot_search",
        )

    def run_task(self, items):
        store = RecordingMarketSnapshotStore()
        provider = MarketSnapshotProvider("akshare", items)
        pool = SearchAgentPool(providers={"akshare": provider}, evidence_store=store)
        envelope = self.make_envelope()
        receipt = pool.submit(envelope, self.make_task())
        pool.run_pending_once()
        status = pool.get_status(envelope, _get_value(receipt, "task_id"))
        return pool, store, receipt, status

    def source_row(self, status, source="akshare"):
        for row in _get_value(status, "source_status"):
            if _get_value(row, "source") == source:
                return row
        self.fail(f"missing source_status row for {source}")

    def events(self, pool, receipt, event_type):
        rows = pool.repository.list_events(_get_value(receipt, "task_id"))
        return [row for row in rows if row["event_type"] == event_type]

    def test_market_snapshot_task_saves_snapshot_without_search_result_ingest(self):
        item = {
            "external_id": "quote_001",
            "snapshot_type": "stock_quote",
            "snapshot_time": "2026-05-13T09:30:00+00:00",
            "fetched_at": "2026-05-13T09:30:01+00:00",
            "metrics": {"price": 218.5, "change_rate": 2.15},
        }

        _, store, _, status = self.run_task([item])

        self.assertEqual("completed", _status_name(_get_value(status, "status")))
        self.assertEqual([], store.ingest_calls)
        self.assertEqual(1, len(store.saved_snapshots))
        snapshot = store.saved_snapshots[0]
        self.assertEqual("stock_quote", snapshot["snapshot_type"])
        self.assertEqual("002594", snapshot["ticker"])
        self.assertEqual(("ent_company_002594",), snapshot["entity_ids"])
        self.assertEqual("akshare", snapshot["source"])
        self.assertEqual({"price": 218.5, "change_rate": 2.15}, snapshot["metrics"])

    def test_market_snapshot_missing_required_fields_is_rejected_without_saving(self):
        item = {
            "external_id": "quote_missing_type",
            "snapshot_time": "2026-05-13T09:30:00+00:00",
            "metrics": {"price": 218.5},
        }

        pool, store, receipt, status = self.run_task([item])

        self.assertEqual([], store.ingest_calls)
        self.assertEqual([], store.saved_snapshots)
        source = self.source_row(status)
        self.assertEqual(1, _get_value(source, "found_count"))
        self.assertEqual(0, _get_value(source, "ingested_count"))
        self.assertEqual(1, _get_value(source, "rejected_count"))
        rejected = self.events(pool, receipt, "search.item_rejected")
        self.assertEqual(1, len(rejected))
        self.assertEqual("missing_market_snapshot_field", rejected[0]["payload"]["reason"])
        self.assertEqual(["snapshot_type"], rejected[0]["payload"]["missing_fields"])

    def test_market_snapshot_partial_failure_keeps_valid_snapshot_and_reports_rejections(self):
        valid = {
            "external_id": "quote_valid",
            "snapshot_type": "stock_quote",
            "snapshot_time": "2026-05-13T09:30:00+00:00",
            "metrics": {"price": 218.5},
        }
        missing_metrics = {
            "external_id": "quote_missing_metrics",
            "snapshot_type": "stock_quote",
            "snapshot_time": "2026-05-13T09:30:00+00:00",
        }
        directional = {
            "external_id": "quote_directional",
            "snapshot_type": "stock_quote",
            "snapshot_time": "2026-05-13T09:30:00+00:00",
            "metrics": {"price": 218.5, "recommendation": "buy"},
        }

        pool, store, receipt, status = self.run_task([valid, missing_metrics, directional])

        self.assertEqual(1, len(store.saved_snapshots))
        source = self.source_row(status)
        self.assertEqual(3, _get_value(source, "found_count"))
        self.assertEqual(1, _get_value(source, "ingested_count"))
        self.assertEqual(2, _get_value(source, "rejected_count"))
        reasons = [event["payload"]["reason"] for event in self.events(pool, receipt, "search.item_rejected")]
        self.assertEqual(
            ["missing_market_snapshot_field", "write_boundary_violation"],
            reasons,
        )


def _find_forbidden_key(value, path=""):
    forbidden = {
        "action",
        "bearish",
        "bullish",
        "buy",
        "hold",
        "investment_action",
        "net_impact",
        "recommendation",
        "sell",
        "signal",
        "suggested_action",
        "trade_signal",
        "trading_signal",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text.strip().lower() in forbidden:
                return child_path
            found = _find_forbidden_key(child, child_path)
            if found is not None:
                return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            found = _find_forbidden_key(child, f"{path}[{index}]")
            if found is not None:
                return found
    return None


if __name__ == "__main__":
    unittest.main()
