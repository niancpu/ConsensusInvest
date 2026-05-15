import importlib
import unittest
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone


def _get_value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _status_name(value):
    value = _get_value(value, "value", value)
    return str(value)


def _to_plain(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_plain(asdict(obj))
    if isinstance(obj, dict):
        return {key: _to_plain(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(value) for value in obj]
    if hasattr(obj, "__dict__"):
        return {
            key: _to_plain(value)
            for key, value in vars(obj).items()
            if not key.startswith("_")
        }
    return obj


def _contains_key(obj, forbidden_key):
    plain = _to_plain(obj)
    if isinstance(plain, dict):
        return forbidden_key in plain or any(
            _contains_key(value, forbidden_key) for value in plain.values()
        )
    if isinstance(plain, list):
        return any(_contains_key(value, forbidden_key) for value in plain)
    return False


class FakeProvider:
    def __init__(self, source, *, items=None, fails=False, expansion_requests=None):
        self.source = source
        self.items = items or [
            {
                "external_id": f"{source}_001",
                "title": f"{source} result",
                "url": f"https://example.com/{source}/001",
                "content": "provider content",
                "content_preview": "provider preview",
                "publish_time": "2026-05-12T10:00:00+08:00",
                "fetched_at": "2026-05-13T10:00:00+08:00",
                "language": "zh-CN",
                "raw_payload": {"provider_response": {"source": source}},
            }
        ]
        self.fails = fails
        self.expansion_requests = expansion_requests or []
        self.search_calls = []
        self.expand_calls = []

    def search(self, envelope, task):
        self.search_calls.append((envelope, task))
        if self.fails:
            raise RuntimeError(f"{self.source} unavailable")
        return {
            "task_id": None,
            "worker_id": f"worker_{self.source}",
            "source": self.source,
            "source_type": "web_news",
            "target": _get_value(task, "target", {}),
            "items": deepcopy(self.items),
            "expansion_requests": deepcopy(self.expansion_requests),
            "completed_at": "2026-05-13T10:00:01+08:00",
        }

    def expand(self, envelope, task, action, seed_item=None):
        self.expand_calls.append(
            {
                "action": action,
                "seed_item": seed_item,
                "envelope": envelope,
                "task": task,
            }
        )
        return {
            "task_id": None,
            "worker_id": f"worker_{self.source}_expand",
            "source": self.source,
            "source_type": "web_news",
            "target": _get_value(task, "target", {}),
            "items": [],
            "completed_at": "2026-05-13T10:00:02+08:00",
        }


class RecordingEvidenceStore:
    def __init__(self):
        self.ingest_calls = []

    def ingest_search_result(self, envelope, package):
        self.ingest_calls.append((envelope, package))
        source = _get_value(package, "source", "unknown")
        return {
            "task_id": _get_value(package, "task_id"),
            "workflow_run_id": _get_value(envelope, "workflow_run_id"),
            "status": "accepted",
            "accepted_raw_refs": [f"raw_{source}_001"],
            "created_evidence_ids": [f"ev_{source}_001"],
            "updated_evidence_ids": [],
            "rejected_items": [],
        }


class SearchAgentPoolContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime_models = importlib.import_module("consensusinvest.runtime.models")
        cls.search_models = importlib.import_module("consensusinvest.search_agent.models")
        cls.pool_module = importlib.import_module("consensusinvest.search_agent.pool")
        cls.providers_module = importlib.import_module(
            "consensusinvest.search_agent.providers"
        )
        cls.evidence_client_module = importlib.import_module(
            "consensusinvest.evidence_store.client"
        )

    def make_envelope(self, *, idempotency_key="search_002594_contract"):
        payload = {
            "request_id": "req_contract_001",
            "correlation_id": "corr_contract_001",
            "workflow_run_id": None,
            "analysis_time": datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            "requested_by": "workflow_orchestrator",
            "idempotency_key": idempotency_key,
            "trace_level": "standard",
        }
        envelope_cls = getattr(self.runtime_models, "InternalCallEnvelope", None)
        if envelope_cls is None:
            return payload
        return envelope_cls(**payload)

    def make_task(
        self,
        *,
        sources,
        idempotency_key="search_002594_contract",
        max_results=50,
        max_provider_calls=20,
        allowed_actions=None,
        ingest_target="evidence_store",
    ):
        payload = {
            "task_type": "stock_research",
            "target": {
                "ticker": "002594",
                "stock_code": "002594.SZ",
                "entity_id": "ent_company_002594",
                "keywords": ["BYD"],
            },
            "scope": {
                "sources": list(sources),
                "evidence_types": ["company_news"],
                "lookback_days": 30,
                "max_results": max_results,
            },
            "constraints": {
                "allow_stale_cache": True,
                "dedupe_hint": True,
                "language": "zh-CN",
                "expansion_policy": {
                    "allowed": True,
                    "max_depth": 1,
                    "allowed_actions": allowed_actions
                    if allowed_actions is not None
                    else [
                        "fetch_original_url",
                        "follow_official_source",
                        "provider_pagination",
                        "same_event_cross_source",
                    ],
                },
                "budget": {
                    "max_provider_calls": max_provider_calls,
                    "max_runtime_ms": 60000,
                },
            },
            "callback": {
                "ingest_target": ingest_target,
                "workflow_run_id": None,
            },
            "idempotency_key": idempotency_key,
        }
        task_cls = getattr(self.search_models, "SearchTask", None)
        if task_cls is None:
            return payload
        return task_cls(**payload)

    def make_pool(self, providers, evidence_store):
        pool_cls = getattr(self.pool_module, "SearchAgentPool")
        provider_registry = {provider.source: provider for provider in providers}
        constructor_attempts = [
            lambda: pool_cls(providers=provider_registry, evidence_store=evidence_store),
            lambda: pool_cls(
                provider_registry=provider_registry,
                evidence_store_client=evidence_store,
            ),
            lambda: pool_cls(provider_registry, evidence_store),
        ]
        last_error = None
        for attempt in constructor_attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_error = exc
        raise last_error

    def submit_and_run(self, pool, envelope, task):
        receipt = pool.submit(envelope, task)
        task_id = _get_value(receipt, "task_id")
        self.assertTrue(task_id)
        for method_name in (
            "run_until_idle",
            "drain",
            "process_all",
            "run_pending_once",
            "execute_task",
        ):
            method = getattr(pool, method_name, None)
            if method is None:
                continue
            try:
                method(task_id)
            except TypeError:
                method()
        return receipt, pool.get_status(envelope, task_id)

    def source_rows(self, status):
        rows = _get_value(status, "source_status", None)
        self.assertIsInstance(rows, list)
        return rows

    def source_row(self, status, source):
        for row in self.source_rows(status):
            if _get_value(row, "source") == source:
                return row
        self.fail(f"missing source_status row for {source}")

    def assert_task_status(self, status, expected):
        self.assertEqual(expected, _status_name(_get_value(status, "status")))

    def events_for_receipt(self, pool, receipt):
        task_id = _get_value(receipt, "task_id")
        repository = _get_value(pool, "repository")
        self.assertIsNotNone(repository)
        list_events = getattr(repository, "list_events", None)
        self.assertTrue(callable(list_events))
        return list_events(task_id)

    def test_submit_is_idempotent_for_same_idempotency_key(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily")
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope(idempotency_key="search_same_key")
        task = self.make_task(sources=["tavily"], idempotency_key="search_same_key")

        first_receipt = pool.submit(envelope, task)
        second_receipt = pool.submit(envelope, deepcopy(task))

        self.assertEqual(
            _get_value(first_receipt, "task_id"),
            _get_value(second_receipt, "task_id"),
        )
        self.assertEqual("search_same_key", _get_value(second_receipt, "idempotency_key"))

    def test_all_sources_success_marks_task_completed_and_ingests_each_source(self):
        evidence_store = RecordingEvidenceStore()
        pool = self.make_pool(
            [FakeProvider("tavily"), FakeProvider("exa")], evidence_store
        )
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily", "exa"])

        _, status = self.submit_and_run(pool, envelope, task)

        self.assert_task_status(status, "completed")
        self.assertEqual(2, len(evidence_store.ingest_calls))
        self.assertEqual("completed", _status_name(_get_value(self.source_row(status, "tavily"), "status")))
        self.assertEqual("completed", _status_name(_get_value(self.source_row(status, "exa"), "status")))

    def test_ingested_search_result_package_matches_contract_fields(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily")
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily"])

        receipt, _ = self.submit_and_run(pool, envelope, task)

        self.assertEqual(1, len(evidence_store.ingest_calls))
        _, package = evidence_store.ingest_calls[0]
        self.assertEqual(_get_value(receipt, "task_id"), _get_value(package, "task_id"))
        self.assertEqual("worker_tavily", _get_value(package, "worker_id"))
        self.assertEqual("tavily", _get_value(package, "source"))
        self.assertEqual("web_news", _get_value(package, "source_type"))
        self.assertEqual("2026-05-13T10:00:01+08:00", _get_value(package, "completed_at"))

        items = list(_get_value(package, "items"))
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("tavily_001", _get_value(item, "external_id"))
        self.assertEqual("tavily result", _get_value(item, "title"))
        self.assertEqual("https://example.com/tavily/001", _get_value(item, "url"))
        self.assertEqual("provider content", _get_value(item, "content"))
        self.assertEqual("provider preview", _get_value(item, "content_preview"))
        self.assertEqual("2026-05-12T10:00:00+08:00", _get_value(item, "publish_time"))
        self.assertEqual("2026-05-13T10:00:00+08:00", _get_value(item, "fetched_at"))
        self.assertEqual("zh-CN", _get_value(item, "language"))
        self.assertEqual(
            {"provider_response": {"source": "tavily"}},
            _get_value(item, "raw_payload"),
        )

    def test_search_agent_events_use_protocol_names(self):
        evidence_store = RecordingEvidenceStore()
        pool = self.make_pool([FakeProvider("tavily")], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily"])

        receipt, _ = self.submit_and_run(pool, envelope, task)

        event_types = [event["event_type"] for event in self.events_for_receipt(pool, receipt)]
        for expected in (
            "search.task_queued",
            "search.source_started",
            "search.item_found",
            "search.item_ingested",
            "search.task_completed",
        ):
            self.assertIn(expected, event_types)
        for old_name in (
            "task_queued",
            "task_running",
            "task_finished",
            "source_failed",
        ):
            self.assertNotIn(old_name, event_types)

    def test_single_source_failure_marks_task_partial_completed(self):
        evidence_store = RecordingEvidenceStore()
        pool = self.make_pool(
            [FakeProvider("tavily"), FakeProvider("exa", fails=True)],
            evidence_store,
        )
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily", "exa"])

        _, status = self.submit_and_run(pool, envelope, task)

        self.assert_task_status(status, "partial_completed")
        self.assertEqual(1, len(evidence_store.ingest_calls))
        self.assertEqual("completed", _status_name(_get_value(self.source_row(status, "tavily"), "status")))
        self.assertEqual("failed", _status_name(_get_value(self.source_row(status, "exa"), "status")))
        self.assertIn("unavailable", _get_value(status, "last_error", ""))

    def test_all_sources_failed_marks_task_failed_without_ingest(self):
        evidence_store = RecordingEvidenceStore()
        pool = self.make_pool(
            [FakeProvider("tavily", fails=True), FakeProvider("exa", fails=True)],
            evidence_store,
        )
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily", "exa"])

        _, status = self.submit_and_run(pool, envelope, task)

        self.assert_task_status(status, "failed")
        self.assertEqual([], evidence_store.ingest_calls)
        self.assertEqual("failed", _status_name(_get_value(self.source_row(status, "tavily"), "status")))
        self.assertEqual("failed", _status_name(_get_value(self.source_row(status, "exa"), "status")))
        self.assertIn("unavailable", _get_value(status, "last_error", ""))

    def test_max_provider_calls_budget_limits_provider_execution(self):
        evidence_store = RecordingEvidenceStore()
        tavily = FakeProvider("tavily")
        exa = FakeProvider("exa")
        pool = self.make_pool([tavily, exa], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily", "exa"], max_provider_calls=1)

        _, status = self.submit_and_run(pool, envelope, task)

        total_provider_calls = len(tavily.search_calls) + len(exa.search_calls)
        self.assertLessEqual(total_provider_calls, 1)
        self.assertEqual(1, len(evidence_store.ingest_calls))
        rows = {row["source"] if isinstance(row, dict) else row.source: row for row in self.source_rows(status)}
        self.assertIn("tavily", rows)
        self.assertIn("exa", rows)
        row_statuses = {_status_name(_get_value(row, "status")) for row in rows.values()}
        self.assertIn("completed", row_statuses)
        self.assertTrue(
            {"skipped", "budget_exhausted", "cancelled", "failed"} & row_statuses
        )

    def test_scope_max_results_limits_items_sent_to_evidence_store(self):
        items = [
            {
                "external_id": f"tavily_{index:03d}",
                "title": f"tavily result {index}",
                "url": f"https://example.com/tavily/{index:03d}",
                "content": f"provider content {index}",
                "content_preview": f"provider preview {index}",
                "publish_time": "2026-05-12T10:00:00+08:00",
                "fetched_at": "2026-05-13T10:00:00+08:00",
                "language": "zh-CN",
                "raw_payload": {"provider_response": {"source": "tavily", "index": index}},
            }
            for index in range(1, 5)
        ]
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily", items=items)
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily"], max_results=2)

        _, status = self.submit_and_run(pool, envelope, task)

        self.assert_task_status(status, "completed")
        self.assertEqual(1, len(evidence_store.ingest_calls))
        _, package = evidence_store.ingest_calls[0]
        package_items = list(_get_value(package, "items"))
        self.assertEqual(2, len(package_items))
        self.assertEqual(["tavily_001", "tavily_002"], [_get_value(item, "external_id") for item in package_items])
        self.assertEqual(2, _get_value(self.source_row(status, "tavily"), "found_count"))

    def test_submit_rejects_callback_ingest_target_outside_evidence_store(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily")
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily"], ingest_target="report_module")

        with self.assertRaises(ValueError):
            pool.submit(envelope, task)

        self.assertEqual([], provider.search_calls)
        self.assertEqual([], evidence_store.ingest_calls)

    def test_disallowed_expansion_action_is_skipped(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider(
            "tavily",
            expansion_requests=[
                {
                    "action": "new_investment_thesis",
                    "reason": "outside first-version Search Agent boundary",
                }
            ],
        )
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(
            sources=["tavily"],
            allowed_actions=["fetch_original_url"],
        )

        _, status = self.submit_and_run(pool, envelope, task)

        self.assert_task_status(status, "completed")
        self.assertEqual([], provider.expand_calls)
        source_status = self.source_row(status, "tavily")
        skipped_actions = _get_value(source_status, "skipped_expansion_actions", [])
        self.assertIn("new_investment_thesis", skipped_actions)

    def test_get_status_reports_source_status_without_evidence_ids(self):
        evidence_store = RecordingEvidenceStore()
        pool = self.make_pool([FakeProvider("tavily")], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily"])

        _, status = self.submit_and_run(pool, envelope, task)

        self.assertEqual(1, len(self.source_rows(status)))
        source_status = self.source_row(status, "tavily")
        self.assertEqual("tavily", _get_value(source_status, "source"))
        self.assertFalse(_contains_key(status, "evidence_id"))
        self.assertFalse(_contains_key(status, "created_evidence_ids"))
        self.assertFalse(_contains_key(status, "updated_evidence_ids"))

    def test_get_status_includes_lifecycle_timestamps_and_last_error(self):
        evidence_store = RecordingEvidenceStore()
        pool = self.make_pool(
            [FakeProvider("tavily"), FakeProvider("exa", fails=True)],
            evidence_store,
        )
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily", "exa"])

        _, status = self.submit_and_run(pool, envelope, task)

        self.assert_task_status(status, "partial_completed")
        self.assertTrue(_get_value(status, "started_at"))
        self.assertTrue(_get_value(status, "completed_at"))
        self.assertIn("exa unavailable", _get_value(status, "last_error", ""))

    def test_waiting_status_persists_without_completed_at_and_restores_idempotency(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily")
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope(idempotency_key="search_waiting_key")
        task = self.make_task(sources=["tavily"], idempotency_key="search_waiting_key")
        status_enum = self.search_models.SearchTaskStatus

        receipt = pool.submit(envelope, task)
        task_id = _get_value(receipt, "task_id")
        pool.repository.update_task_status(task_id, status_enum.WAITING)

        status = pool.get_status(envelope, task_id)
        restored_receipt = pool.submit(envelope, deepcopy(task))

        self.assert_task_status(status, "waiting")
        self.assertIsNone(_get_value(status, "completed_at"))
        self.assertEqual(task_id, _get_value(restored_receipt, "task_id"))
        self.assertEqual("waiting", _status_name(_get_value(restored_receipt, "status")))
        self.assertEqual([], provider.search_calls)
        self.assertEqual([], evidence_store.ingest_calls)

    def test_cancelled_status_persists_completed_at_and_is_not_executed(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily")
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope(idempotency_key="search_cancelled_key")
        task = self.make_task(sources=["tavily"], idempotency_key="search_cancelled_key")
        status_enum = self.search_models.SearchTaskStatus

        receipt = pool.submit(envelope, task)
        task_id = _get_value(receipt, "task_id")
        pool.repository.update_task_status(task_id, status_enum.CANCELLED)

        executed_task_ids = pool.run_pending_once()
        status = pool.get_status(envelope, task_id)
        restored_receipt = pool.submit(envelope, deepcopy(task))

        self.assertEqual([], executed_task_ids)
        self.assert_task_status(status, "cancelled")
        self.assertTrue(_get_value(status, "completed_at"))
        self.assertEqual(task_id, _get_value(restored_receipt, "task_id"))
        self.assertEqual("cancelled", _status_name(_get_value(restored_receipt, "status")))
        self.assertEqual([], provider.search_calls)
        self.assertEqual([], evidence_store.ingest_calls)

    def test_run_task_once_retries_failed_task(self):
        evidence_store = RecordingEvidenceStore()
        provider = FakeProvider("tavily")
        pool = self.make_pool([provider], evidence_store)
        envelope = self.make_envelope(idempotency_key="search_failed_retry_key")
        task = self.make_task(sources=["tavily"], idempotency_key="search_failed_retry_key")
        status_enum = self.search_models.SearchTaskStatus

        receipt = pool.submit(envelope, task)
        task_id = _get_value(receipt, "task_id")
        pool.repository.update_task_status(task_id, status_enum.FAILED)

        executed = pool.run_task_once(task_id)
        status = pool.get_status(envelope, task_id)

        self.assertTrue(executed)
        self.assert_task_status(status, "completed")
        self.assertEqual(1, len(provider.search_calls))

    def test_pool_consumes_evidence_store_ingest_result_without_exposing_ids(self):
        evidence_store = self.evidence_client_module.FakeEvidenceStoreClient()
        pool = self.make_pool([FakeProvider("tavily")], evidence_store)
        envelope = self.make_envelope()
        task = self.make_task(sources=["tavily"])

        _, status = self.submit_and_run(pool, envelope, task)

        source_status = self.source_row(status, "tavily")
        self.assertEqual(1, _get_value(source_status, "found_count"))
        self.assertEqual(1, _get_value(source_status, "ingested_count"))
        self.assertEqual(0, _get_value(source_status, "rejected_count"))
        self.assertEqual(1, len(evidence_store.received_packages))
        self.assertFalse(_contains_key(status, "accepted_raw_refs"))
        self.assertFalse(_contains_key(status, "created_evidence_ids"))


if __name__ == "__main__":
    unittest.main()
