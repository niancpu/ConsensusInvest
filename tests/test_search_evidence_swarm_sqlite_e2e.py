import tempfile
import unittest
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from consensusinvest.agent_swarm import AgentSwarmRuntime, JudgeRuntime
from consensusinvest.evidence_store import SQLiteEvidenceStoreClient
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent import SearchAgentPool
from consensusinvest.search_agent.models import SearchTask


def _get_value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _status_name(value):
    return str(_get_value(value, "value", value))


def _to_plain(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_plain(asdict(obj))
    if isinstance(obj, dict):
        return {key: _to_plain(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(value) for value in obj]
    return obj


def _contains_key(obj, key):
    plain = _to_plain(obj)
    if isinstance(plain, dict):
        return key in plain or any(_contains_key(value, key) for value in plain.values())
    if isinstance(plain, list):
        return any(_contains_key(value, key) for value in plain)
    return False


class SQLiteE2EProvider:
    source = "tavily"

    def search(self, envelope, task):
        del envelope, task
        return {
            "worker_id": "worker_tavily_e2e",
            "source_type": "web_news",
            "items": [
                {
                    "external_id": "news_001",
                    "title": "BYD margin improved",
                    "url": "https://example.com/news/001",
                    "content": "BYD reported margin improvement.",
                    "content_preview": "Margin improvement.",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "fetched_at": "2026-05-13T09:00:00+00:00",
                    "language": "en",
                    "source_quality_hint": 0.86,
                    "relevance": 0.91,
                    "metadata": {"evidence_type": "company_news"},
                },
                {
                    "external_id": "news_002",
                    "title": "BYD cash flow needs checking",
                    "url": "https://example.com/news/002",
                    "content": "BYD cash flow quality still needs checking.",
                    "content_preview": "Cash flow needs checking.",
                    "publish_time": "2026-05-12T11:00:00+00:00",
                    "fetched_at": "2026-05-13T09:10:00+00:00",
                    "language": "en",
                    "source_quality_hint": 0.74,
                    "relevance": 0.83,
                    "metadata": {"evidence_type": "company_news"},
                },
            ],
            "completed_at": "2026-05-13T09:30:00+00:00",
        }

    def expand(self, envelope, task, action, seed_item=None):
        del envelope, task, action, seed_item
        return {"items": []}


class SearchEvidenceSwarmSQLiteE2ETests(unittest.TestCase):
    def make_envelope(self, *, idempotency_key):
        return InternalCallEnvelope(
            request_id=f"req_{idempotency_key}",
            correlation_id="corr_e2e_001",
            workflow_run_id="wr_e2e_001",
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key=idempotency_key,
            trace_level="standard",
        )

    def make_search_task(self):
        return SearchTask(
            task_type="stock_research",
            target={
                "ticker": "002594",
                "stock_code": "002594.SZ",
                "entity_id": "ent_company_002594",
                "keywords": ["BYD"],
            },
            scope={
                "sources": ["tavily"],
                "evidence_types": ["company_news"],
                "lookback_days": 30,
                "max_results": 2,
            },
            constraints={
                "expansion_policy": {"allowed": False, "max_depth": 0, "allowed_actions": []},
                "budget": {"max_provider_calls": 1, "max_runtime_ms": 60000},
            },
            callback={"ingest_target": "evidence_store", "workflow_run_id": "wr_e2e_001"},
            idempotency_key="search_e2e_001",
        )

    def test_search_agent_ingests_to_sqlite_then_swarm_and_judge_save_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteEvidenceStoreClient(Path(tmpdir) / "evidence.db")
            pool = SearchAgentPool(
                providers={"tavily": SQLiteE2EProvider()},
                evidence_store=store,
            )
            search_envelope = self.make_envelope(idempotency_key="search_e2e_001")

            receipt = pool.submit(search_envelope, self.make_search_task())
            pool.run_pending_once()
            status = pool.get_status(search_envelope, receipt.task_id)

            self.assertEqual("completed", _status_name(_get_value(status, "status")))
            self.assertFalse(_contains_key(status, "evidence_id"))
            self.assertFalse(_contains_key(status, "created_evidence_ids"))

            page = store.query_evidence(
                search_envelope,
                {
                    "workflow_run_id": "wr_e2e_001",
                    "ticker": "002594",
                    "entity_ids": ["ent_company_002594"],
                    "evidence_types": ["company_news"],
                },
            )
            evidence_ids = [item.evidence_id for item in page.items]
            self.assertEqual(["ev_000002", "ev_000001"], evidence_ids)

            swarm = AgentSwarmRuntime(evidence_store=store)
            swarm_outcome = swarm.run(
                self.make_envelope(idempotency_key="swarm_e2e_001"),
                {
                    "workflow_run_id": "wr_e2e_001",
                    "ticker": "002594",
                    "entity_id": "ent_company_002594",
                    "workflow_config_id": "mvp_bull_judge_v1",
                    "evidence_selection": {"evidence_ids": evidence_ids},
                },
            )
            self.assertEqual("completed", swarm_outcome.status)

            judge = JudgeRuntime(evidence_store=store, repository=swarm.repository)
            judge_outcome = judge.run(
                self.make_envelope(idempotency_key="judge_e2e_001"),
                {
                    "workflow_run_id": "wr_e2e_001",
                    "round_summary_ids": list(swarm_outcome.round_summary_ids),
                    "agent_argument_ids": list(swarm_outcome.agent_argument_ids),
                    "key_evidence_ids": evidence_ids,
                },
            )
            self.assertEqual("completed", judge_outcome.status)

            refs = store.query_references(
                self.make_envelope(idempotency_key="refs_e2e_001"),
                {"workflow_run_id": "wr_e2e_001"},
            )
            source_types = [ref.source_type for ref in refs]
            self.assertIn("agent_argument", source_types)
            self.assertIn("round_summary", source_types)
            self.assertIn("judgment", source_types)
            self.assertEqual(20, len(refs))
            self.assertEqual({"ev_000001", "ev_000002"}, {ref.evidence_id for ref in refs})
            self.assertEqual({1, 2, 3}, {ref.round for ref in refs if ref.source_type != "judgment"})
            self.assertEqual({None}, {ref.round for ref in refs if ref.source_type == "judgment"})
            store.close()

    def test_swarm_and_judge_reject_missing_sqlite_evidence_ids_without_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteEvidenceStoreClient(Path(tmpdir) / "evidence.db")
            swarm = AgentSwarmRuntime(evidence_store=store)

            swarm_outcome = swarm.run(
                self.make_envelope(idempotency_key="swarm_missing_e2e_001"),
                {
                    "workflow_run_id": "wr_e2e_001",
                    "ticker": "002594",
                    "entity_id": "ent_company_002594",
                    "workflow_config_id": "mvp_bull_judge_v1",
                    "evidence_selection": {"evidence_ids": ["ev_missing"]},
                },
            )
            self.assertEqual("insufficient_evidence", swarm_outcome.status)

            judge = JudgeRuntime(evidence_store=store, repository=swarm.repository)
            judge_outcome = judge.run(
                self.make_envelope(idempotency_key="judge_missing_e2e_001"),
                {
                    "workflow_run_id": "wr_e2e_001",
                    "agent_argument_ids": ["arg_missing"],
                    "key_evidence_ids": ["ev_missing"],
                },
            )
            self.assertEqual("insufficient_evidence", judge_outcome.status)

            refs = store.query_references(
                self.make_envelope(idempotency_key="refs_missing_e2e_001"),
                {"workflow_run_id": "wr_e2e_001"},
            )
            self.assertEqual([], refs)
            store.close()


if __name__ == "__main__":
    unittest.main()
