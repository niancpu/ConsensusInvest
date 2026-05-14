import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from consensusinvest.agent_swarm import (
    AgentArgumentDraft,
    JudgeToolCallRecord,
    JudgmentRecord,
    RoundSummaryDraft,
    SQLiteAgentSwarmRepository,
)
from consensusinvest.evidence_store import EvidenceReference


class SQLiteAgentSwarmRepositoryTests(unittest.TestCase):
    def test_saves_lists_and_reopens_agent_judge_outputs(self):
        created_at = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
        workflow_run_id = "wr_sqlite_agent_001"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agent_swarm.db"
            repo = SQLiteAgentSwarmRepository(db_path)

            run = repo.start_agent_run(
                workflow_run_id=workflow_run_id,
                agent_id="bull_v1",
                role="bullish_interpreter",
                started_at=created_at,
            )
            completed = repo.complete_agent_run(
                run.agent_run_id,
                completed_at=created_at,
                rounds=(1,),
            )
            argument = repo.save_argument(
                workflow_run_id=workflow_run_id,
                agent_run_id=run.agent_run_id,
                draft=AgentArgumentDraft(
                    agent_id="bull_v1",
                    role="bullish_interpreter",
                    round=1,
                    argument="Argument text.",
                    confidence=0.81,
                    referenced_evidence_ids=("ev_000001",),
                    counter_evidence_ids=("ev_000002",),
                    limitations=("Needs cash-flow check.",),
                    role_output={"stance_interpretation": "positive"},
                ),
                created_at=created_at,
            )
            summary = repo.save_round_summary(
                RoundSummaryDraft(
                    workflow_run_id=workflow_run_id,
                    round=1,
                    summary="Round summary.",
                    participants=("bull_v1",),
                    agent_argument_ids=(argument.agent_argument_id,),
                    referenced_evidence_ids=("ev_000001",),
                    disputed_evidence_ids=("ev_000002",),
                ),
                created_at=created_at,
            )
            judgment = repo.save_judgment(
                JudgmentRecord(
                    judgment_id=repo.new_judgment_id(),
                    workflow_run_id=workflow_run_id,
                    final_signal="neutral",
                    confidence=0.74,
                    time_horizon="short_to_mid_term",
                    key_positive_evidence_ids=("ev_000001",),
                    key_negative_evidence_ids=("ev_000002",),
                    reasoning="Reasoning.",
                    risk_notes=("Risk.",),
                    suggested_next_checks=("Next check.",),
                    referenced_agent_argument_ids=(argument.agent_argument_id,),
                    limitations=("Limitation.",),
                    created_at=created_at,
                )
            )
            tool_call = repo.save_tool_call(
                JudgeToolCallRecord(
                    tool_call_id=repo.new_tool_call_id(),
                    judgment_id=judgment.judgment_id,
                    tool_name="get_evidence_detail",
                    input={"evidence_id": "ev_000001"},
                    result_ref={"evidence_id": "ev_000001", "raw_ref": "raw_000001"},
                    output_summary="source_quality=0.9.",
                    referenced_evidence_ids=("ev_000001",),
                    used_for="verify_key_evidence",
                    created_at=created_at,
                )
            )
            repo.save_references(
                [
                    EvidenceReference(
                        reference_id="eref_sqlite_001",
                        source_type="agent_argument",
                        source_id=argument.agent_argument_id,
                        evidence_id="ev_000001",
                        reference_role="supports",
                        round=1,
                        workflow_run_id=workflow_run_id,
                        created_at=created_at,
                    ),
                    EvidenceReference(
                        reference_id="eref_sqlite_002",
                        source_type="judgment",
                        source_id=judgment.judgment_id,
                        evidence_id="ev_000002",
                        reference_role="counters",
                        workflow_run_id=workflow_run_id,
                        created_at=created_at,
                    ),
                ]
            )

            self.assertEqual("completed", completed.status)
            self.assertEqual([run.agent_run_id], [item.agent_run_id for item in repo.list_agent_runs(workflow_run_id)])
            self.assertEqual([argument.agent_argument_id], [item.agent_argument_id for item in repo.list_arguments(workflow_run_id)])
            self.assertEqual(
                [argument.agent_argument_id],
                [item.agent_argument_id for item in repo.list_arguments(workflow_run_id, agent_id="bull_v1", round=1)],
            )
            self.assertEqual([], repo.list_arguments(workflow_run_id, agent_id="bear_v1"))
            self.assertEqual(summary, repo.get_round_summary(summary.round_summary_id))
            self.assertEqual(judgment, repo.get_judgment_by_workflow(workflow_run_id))
            self.assertEqual([tool_call], repo.list_tool_calls(judgment.judgment_id))
            self.assertEqual(
                ["eref_sqlite_001"],
                [
                    ref.reference_id
                    for ref in repo.list_references(
                        source_type="agent_argument",
                        source_id=argument.agent_argument_id,
                    )
                ],
            )
            repo.close()

            reopened = SQLiteAgentSwarmRepository(db_path)
            try:
                self.assertEqual([completed], reopened.list_agent_runs(workflow_run_id))
                self.assertEqual(argument, reopened.get_argument(argument.agent_argument_id))
                self.assertEqual([summary], reopened.list_round_summaries(workflow_run_id))
                self.assertEqual(judgment, reopened.get_judgment(judgment.judgment_id))
                self.assertEqual([tool_call], reopened.list_tool_calls(judgment.judgment_id))
                self.assertEqual(
                    ["eref_sqlite_001", "eref_sqlite_002"],
                    [ref.reference_id for ref in reopened.list_references(workflow_run_id=workflow_run_id)],
                )
                self.assertEqual("jdg_000002", reopened.new_judgment_id())
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
