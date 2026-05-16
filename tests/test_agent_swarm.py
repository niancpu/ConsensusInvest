import unittest
from datetime import datetime, timezone

from consensusinvest.agent_swarm import (
    AgentSwarmRuntime,
    JudgeRuntime,
)
from consensusinvest.evidence_store import FakeEvidenceStoreClient
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.search_agent.models import SearchResultPackage, SearchTarget


class FakeLLMProvider:
    def __init__(self) -> None:
        self.calls = []

    def complete_json(self, *, purpose, system_prompt, user_payload, model=None):
        self.calls.append(
            {
                "purpose": purpose,
                "system_prompt": system_prompt,
                "user_payload": user_payload,
                "model": model,
            }
        )
        if purpose == "agent_argument":
            return {
                "argument": "LLM argument grounded in allowed Evidence only.",
                "confidence": 0.93,
                "referenced_evidence_ids": ["ev_000001", "ev_fake"],
                "counter_evidence_ids": ["ev_000002", "ev_fake"],
                "limitations": ["LLM limitation"],
                "role_output": {"stance_interpretation": "LLM stance"},
            }
        if purpose == "round_summary":
            return {"summary": "LLM round summary without new facts."}
        if purpose == "judge":
            return {
                "final_signal": "bullish",
                "confidence": 0.91,
                "time_horizon": "mid_term",
                "key_positive_evidence_ids": ["ev_000001", "ev_fake"],
                "key_negative_evidence_ids": ["ev_000002"],
                "reasoning": "LLM judgment grounded in saved arguments and Evidence.",
                "risk_notes": ["LLM risk"],
                "suggested_next_checks": ["LLM next check"],
                "referenced_agent_argument_ids": ["arg_000001", "arg_fake"],
                "limitations": ["LLM judge limitation"],
            }
        raise AssertionError(f"unexpected purpose: {purpose}")


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

    def test_swarm_uses_llm_provider_and_filters_unowned_evidence_ids(self):
        store = self.make_store()
        llm = FakeLLMProvider()
        runtime = AgentSwarmRuntime(evidence_store=store, llm_provider=llm)

        outcome = runtime.run(
            self.make_envelope(idempotency_key="run_llm_swarm"),
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "ticker": "002594",
                "entity_id": "ent_company_002594",
                "workflow_config_id": "mvp_bull_judge_v1",
                "evidence_selection": {"evidence_ids": ["ev_000001", "ev_000002"]},
            },
        )

        self.assertEqual("completed", outcome.status)
        first_argument = runtime.repository.get_argument(outcome.agent_argument_ids[0])
        self.assertIsNotNone(first_argument)
        assert first_argument is not None
        self.assertIn("第 1/3 轮", first_argument.argument)
        self.assertIn("比亚迪", first_argument.argument)
        self.assertEqual(("ev_000001",), first_argument.referenced_evidence_ids)
        self.assertEqual(("ev_000002",), first_argument.counter_evidence_ids)
        self.assertIn("第 1/3 轮", runtime.repository.list_round_summaries("wr_agent_swarm_001")[0].summary)
        self.assertEqual(["agent_argument", "round_summary"] * 3, [call["purpose"] for call in llm.calls])
        agent_prompt = next(call["system_prompt"] for call in llm.calls if call["purpose"] == "agent_argument")
        summary_prompt = next(call["system_prompt"] for call in llm.calls if call["purpose"] == "round_summary")
        self.assertIn("必须使用简体中文", agent_prompt)
        self.assertIn("必须使用简体中文", summary_prompt)
        self.assertEqual("zh-CN", llm.calls[0]["user_payload"]["language"])
        self.assertEqual("zh-CN", llm.calls[1]["user_payload"]["language"])
        self.assertIn("只允许简体中文", llm.calls[0]["user_payload"]["output_schema"]["argument"])
        self.assertIn("只允许简体中文", llm.calls[1]["user_payload"]["output_schema"]["summary"])

    def test_swarm_llm_payload_repairs_reused_numeric_evidence_from_raw_payload(self):
        store = FakeEvidenceStoreClient()
        envelope = self.make_envelope(idempotency_key="seed_numeric_evidence")
        package = SearchResultPackage(
            task_id="st_numeric_001",
            worker_id="worker_akshare",
            source="akshare",
            source_type="market_data",
            target=SearchTarget(
                ticker="002594",
                stock_code="002594.SZ",
                entity_id="ent_company_002594",
                keywords=("比亚迪",),
            ),
            items=(
                {
                    "external_id": "ak_numeric_001",
                    "title": "AkShare stock_financial_abstract 002594",
                    "url": "akshare://stock_financial_abstract/002594",
                    "content": "13.33 606.70 7280.40 11 12.00 -9.98 301042",
                    "publish_time": "2026-05-12T10:00:00+00:00",
                    "source_quality_hint": 0.8,
                    "raw_payload": {
                        "provider_response": {
                            "报告期": "2026-03-31",
                            "净利润": 606.70,
                            "营业收入": 7280.40,
                        },
                        "provider_api": "stock_financial_abstract",
                        "provider_symbol": "002594",
                    },
                    "metadata": {"evidence_type": "financial_report"},
                },
            ),
            completed_at="2026-05-13T09:00:00+00:00",
            metadata={"evidence_type": "financial_report"},
        )
        result = store.ingest_search_result(envelope, package)
        llm = FakeLLMProvider()
        runtime = AgentSwarmRuntime(evidence_store=store, llm_provider=llm)

        outcome = runtime.run(
            self.make_envelope(idempotency_key="run_numeric_llm_swarm"),
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "ticker": "002594",
                "entity_id": "ent_company_002594",
                "workflow_config_id": "mvp_bull_judge_v1",
                "evidence_selection": {"evidence_ids": result.created_evidence_ids},
            },
        )

        self.assertEqual("completed", outcome.status)
        evidence_payload = llm.calls[0]["user_payload"]["evidence"][0]
        self.assertIn("akshare 结构化行情/财务数据", evidence_payload["content"].lower())
        self.assertIn("净利润：606.7", evidence_payload["content"])
        self.assertIn("营业收入：7280.4", evidence_payload["objective_summary"])

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

    def test_judge_uses_llm_provider_and_filters_unowned_ids(self):
        store = self.make_store()
        llm = FakeLLMProvider()
        envelope = self.make_envelope(idempotency_key="run_llm_swarm_then_judge")
        swarm = AgentSwarmRuntime(evidence_store=store, llm_provider=llm)
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
        judge = JudgeRuntime(evidence_store=store, repository=swarm.repository, llm_provider=llm)

        outcome = judge.run(
            self.make_envelope(idempotency_key="run_llm_judge"),
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
        assert judgment is not None
        self.assertEqual("bullish", judgment.final_signal)
        self.assertEqual(("ev_000001",), judgment.key_positive_evidence_ids)
        self.assertEqual(("ev_000002",), judgment.key_negative_evidence_ids)
        self.assertEqual(("arg_000001",), judgment.referenced_agent_argument_ids)
        self.assertEqual("基于已保存智能体论证和关键证据形成判断。", judgment.reasoning)
        self.assertEqual((), judgment.risk_notes)
        self.assertEqual((), judgment.suggested_next_checks)
        self.assertIn("裁决模块未直接触发搜索", judgment.limitations[0])
        judge_call = llm.calls[-1]
        self.assertEqual("judge", judge_call["purpose"])
        self.assertIn("必须使用简体中文", judge_call["system_prompt"])
        self.assertEqual("zh-CN", judge_call["user_payload"]["language"])
        self.assertIn("只允许简体中文", judge_call["user_payload"]["output_schema"]["reasoning"])
        self.assertEqual(
            list(swarm_outcome.round_summary_ids),
            judge_call["user_payload"]["round_summary_ids"],
        )
        self.assertEqual(
            list(swarm_outcome.round_summary_ids),
            [
                summary["round_summary_id"]
                for summary in judge_call["user_payload"]["round_summaries"]
            ],
        )

    def test_judge_returns_insufficient_evidence_when_round_summary_missing(self):
        store = self.make_store()
        envelope = self.make_envelope(idempotency_key="run_swarm_for_missing_summary")
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
            self.make_envelope(idempotency_key="run_judge_missing_summary"),
            {
                "workflow_run_id": "wr_agent_swarm_001",
                "round_summary_ids": [
                    swarm_outcome.round_summary_ids[0],
                    "rsum_missing_001",
                ],
                "agent_argument_ids": list(swarm_outcome.agent_argument_ids),
                "key_evidence_ids": ["ev_000001", "ev_000002"],
            },
        )

        self.assertEqual("insufficient_evidence", outcome.status)
        self.assertIsNone(outcome.judgment_id)
        self.assertEqual("missing_round_summaries", outcome.gaps[0].gap_type)
        self.assertIn("rsum_missing_001", outcome.gaps[0].description)


if __name__ == "__main__":
    unittest.main()
