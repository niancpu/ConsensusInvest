import unittest
from datetime import datetime, timezone

from consensusinvest.agent_swarm import (
    AgentSwarmRuntime,
    JudgeRuntime,
)
from consensusinvest.evidence_store import FakeEvidenceStoreClient
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget


class AgentSwarmRuntimeTests(unittest.TestCase):
    def make_envelope(self, *, idempotency_key="agent_swarm") -> InternalCallEnvelope:
        return InternalCallEnvelope(
            request_id="req_agent_swarm_001",
            correlation_id="corr_agent_swarm_001",
            workflow_run_id="wr_agent_swarm_001",
            analysis_time=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            requested_by="workflow_orchestrator",
            idempotency_key=idempotency_key,
            trace_level="standard",
        )

    def make_store(self) -> FakeEvidenceStoreClient:
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope(idempotency_key="seed_evidence")
        package = SearchResultPackage(
            task_id="st_agent_swarm_001",
            worker_id="worker_tavily",
            source="tavily",
            source_type="web_news",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("比亚迪",),
            ),
            items=(
                {
                    "external_id": "news_001",
                    "title": "比亚迪盈利改善",
                    "url": "https://example.com/news/001",
                    "content": "比亚迪公开披露盈利改善。",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "source_quality_hint": 0.86,
                },
                {
                    "external_id": "news_002",
                    "title": "现金流质量待核对",
                    "url": "https://example.com/news/002",
                    "content": "现金流质量仍需核对。",
                    "publish_time": "2026-05-12T11:00:00+00:00",
                    "source_quality_hint": 0.74,
                },
            ),
            completed_at="2026-05-13T09:00:00+00:00",
            metadata={"evidence_type": "company_news"},
        )
        result = store.ingest_search_result(envelope, package)
        self.assertEqual(["ev_000001", "ev_000002"], result.created_evidence_ids)
        return store

    def test_swarm_saves_argument_summary_and_evidence_references(self):
        store = self.make_store()
        envelope = self.make_envelope(idempotency_key="run_swarm")
        runtime = AgentSwarmRuntime(evidence_store=store)

        outcome = runtime.run(
            envelope,
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "ticker": "002594",
                "entity_id": "ent_company_002594",
                "workflow_config_id": "mvp_bull_judge_v1",
                "evidence_selection": {
                    "evidence_ids": ["ev_000001", "ev_000002"],
                    "selection_strategy": "top_relevance_quality_v1",
                },
                "history": {"previous_judgment_ids": []},
            },
        )

        self.assertEqual("completed", outcome.status)
        self.assertEqual(3, len(outcome.agent_argument_ids))
        self.assertEqual(3, len(outcome.round_summary_ids))
        self.assertEqual(outcome.round_summary_ids[-1], outcome.round_summary_id)
        refs = store.query_references(
            envelope,
            {
                "source_type": "agent_argument",
                "source_id": outcome.agent_argument_ids[0],
            },
        )
        self.assertEqual(["supports", "supports"], [ref.reference_role for ref in refs])
        self.assertEqual([1, 1], [ref.round for ref in refs])
        summaries = runtime.repository.list_round_summaries("wr_agent_swarm_001")
        self.assertEqual([1, 2, 3], [summary.round for summary in summaries])
        self.assertEqual(list(outcome.round_summary_ids), [summary.round_summary_id for summary in summaries])
        runs = runtime.repository.list_agent_runs("wr_agent_swarm_001")
        self.assertEqual((1, 2, 3), runs[0].rounds)

    def test_swarm_returns_gap_without_calling_search_when_evidence_empty(self):
        runtime = AgentSwarmRuntime(evidence_store=FakeEvidenceStoreClient())
        outcome = runtime.run(
            self.make_envelope(idempotency_key="run_gap"),
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "ticker": "002594",
                "entity_id": "ent_company_002594",
                "workflow_config_id": "mvp_bull_judge_v1",
                "evidence_selection": {"evidence_ids": []},
            },
        )

        self.assertEqual("insufficient_evidence", outcome.status)
        self.assertEqual("missing_core_evidence", outcome.gaps[0].gap_type)
        self.assertIsNotNone(outcome.gaps[0].suggested_search)

    def test_judge_saves_judgment_tool_calls_and_references(self):
        store = self.make_store()
        envelope = self.make_envelope(idempotency_key="run_swarm_then_judge")
        swarm = AgentSwarmRuntime(evidence_store=store)
        swarm_outcome = swarm.run(
            envelope,
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "ticker": "002594",
                "entity_id": "ent_company_002594",
                "workflow_config_id": "mvp_bull_judge_v1",
                "evidence_selection": {"evidence_ids": ["ev_000001", "ev_000002"]},
            },
        )
        judge = JudgeRuntime(evidence_store=store, repository=swarm.repository)

        outcome = judge.run(
            self.make_envelope(idempotency_key="run_judge"),
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "round_summary_ids": list(swarm_outcome.round_summary_ids),
                "agent_argument_ids": list(swarm_outcome.agent_argument_ids),
                "key_evidence_ids": ["ev_000001", "ev_000002"],
            },
        )

        self.assertEqual("completed", outcome.status)
        judgment = swarm.repository.get_judgment(outcome.judgment_id or "")
        self.assertIsNotNone(judgment)
        self.assertEqual("neutral", judgment.final_signal)
        self.assertEqual(2, len(swarm.repository.list_tool_calls(outcome.judgment_id or "")))
        refs = store.query_references(
            self.make_envelope(idempotency_key="query_refs"),
            {"source_type": "judgment", "source_id": outcome.judgment_id},
        )
        self.assertEqual(["supports", "counters"], [ref.reference_role for ref in refs])


if __name__ == "__main__":
    unittest.main()
