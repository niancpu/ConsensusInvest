"""In-memory Agent Swarm repository used by MVP runtime and API projection."""

from __future__ import annotations

from datetime import UTC, datetime

from consensusinvest.evidence_store import EvidenceReference

from .models import (
    AgentArgumentDraft,
    AgentArgumentRecord,
    AgentRunRecord,
    JudgeToolCallRecord,
    JudgmentRecord,
    RoundSummaryDraft,
    RoundSummaryRecord,
)


class InMemoryAgentSwarmRepository:
    def __init__(self) -> None:
        self._agent_runs: dict[str, AgentRunRecord] = {}
        self._arguments: dict[str, AgentArgumentRecord] = {}
        self._round_summaries: dict[str, RoundSummaryRecord] = {}
        self._judgments: dict[str, JudgmentRecord] = {}
        self._tool_calls: dict[str, JudgeToolCallRecord] = {}
        self._references: list[EvidenceReference] = []
        self._next_agent_run_id = 1
        self._next_argument_id = 1
        self._next_round_summary_id = 1
        self._next_judgment_id = 1
        self._next_tool_call_id = 1

    def start_agent_run(
        self,
        *,
        workflow_run_id: str,
        agent_id: str,
        role: str,
        started_at: datetime,
    ) -> AgentRunRecord:
        run = AgentRunRecord(
            agent_run_id=self._next_id("arun"),
            workflow_run_id=workflow_run_id,
            agent_id=agent_id,
            role=role,
            status="running",
            started_at=started_at,
        )
        self._agent_runs[run.agent_run_id] = run
        return run

    def complete_agent_run(
        self,
        agent_run_id: str,
        *,
        completed_at: datetime,
        rounds: tuple[int, ...],
    ) -> AgentRunRecord:
        current = self._agent_runs[agent_run_id]
        updated = AgentRunRecord(
            agent_run_id=current.agent_run_id,
            workflow_run_id=current.workflow_run_id,
            agent_id=current.agent_id,
            role=current.role,
            status="completed",
            started_at=current.started_at,
            completed_at=completed_at,
            rounds=rounds,
        )
        self._agent_runs[agent_run_id] = updated
        return updated

    def save_argument(
        self,
        *,
        workflow_run_id: str,
        agent_run_id: str,
        draft: AgentArgumentDraft,
        created_at: datetime,
    ) -> AgentArgumentRecord:
        argument = AgentArgumentRecord(
            agent_argument_id=self._next_id("arg"),
            agent_run_id=agent_run_id,
            workflow_run_id=workflow_run_id,
            agent_id=draft.agent_id,
            role=draft.role,
            round=draft.round,
            argument=draft.argument,
            confidence=draft.confidence,
            referenced_evidence_ids=draft.referenced_evidence_ids,
            counter_evidence_ids=draft.counter_evidence_ids,
            limitations=draft.limitations,
            role_output=dict(draft.role_output),
            created_at=created_at,
        )
        self._arguments[argument.agent_argument_id] = argument
        return argument

    def save_round_summary(
        self,
        draft: RoundSummaryDraft,
        *,
        created_at: datetime,
    ) -> RoundSummaryRecord:
        summary = RoundSummaryRecord(
            workflow_run_id=draft.workflow_run_id,
            round=draft.round,
            summary=draft.summary,
            participants=draft.participants,
            agent_argument_ids=draft.agent_argument_ids,
            referenced_evidence_ids=draft.referenced_evidence_ids,
            disputed_evidence_ids=draft.disputed_evidence_ids,
            round_summary_id=self._next_id("rsum"),
            created_at=created_at,
        )
        self._round_summaries[summary.round_summary_id] = summary
        return summary

    def save_judgment(self, judgment: JudgmentRecord) -> JudgmentRecord:
        self._judgments[judgment.judgment_id] = judgment
        return judgment

    def new_judgment_id(self) -> str:
        return self._next_id("jdg")

    def save_tool_call(self, call: JudgeToolCallRecord) -> JudgeToolCallRecord:
        self._tool_calls[call.tool_call_id] = call
        return call

    def new_tool_call_id(self) -> str:
        return self._next_id("jtc")

    def save_references(self, references: list[EvidenceReference]) -> None:
        self._references.extend(references)

    def list_agent_runs(self, workflow_run_id: str) -> list[AgentRunRecord]:
        return [run for run in self._agent_runs.values() if run.workflow_run_id == workflow_run_id]

    def list_arguments(
        self,
        workflow_run_id: str,
        *,
        agent_id: str | None = None,
        round: int | None = None,
    ) -> list[AgentArgumentRecord]:
        rows = [arg for arg in self._arguments.values() if arg.workflow_run_id == workflow_run_id]
        if agent_id is not None:
            rows = [arg for arg in rows if arg.agent_id == agent_id]
        if round is not None:
            rows = [arg for arg in rows if arg.round == round]
        return rows

    def get_argument(self, agent_argument_id: str) -> AgentArgumentRecord | None:
        return self._arguments.get(agent_argument_id)

    def list_round_summaries(self, workflow_run_id: str) -> list[RoundSummaryRecord]:
        return [
            summary
            for summary in self._round_summaries.values()
            if summary.workflow_run_id == workflow_run_id
        ]

    def get_round_summary(self, round_summary_id: str) -> RoundSummaryRecord | None:
        return self._round_summaries.get(round_summary_id)

    def get_judgment(self, judgment_id: str) -> JudgmentRecord | None:
        return self._judgments.get(judgment_id)

    def get_judgment_by_workflow(self, workflow_run_id: str) -> JudgmentRecord | None:
        for judgment in self._judgments.values():
            if judgment.workflow_run_id == workflow_run_id:
                return judgment
        return None

    def list_tool_calls(self, judgment_id: str) -> list[JudgeToolCallRecord]:
        return [call for call in self._tool_calls.values() if call.judgment_id == judgment_id]

    def list_references(
        self,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> list[EvidenceReference]:
        rows = self._references
        if source_type is not None:
            rows = [ref for ref in rows if ref.source_type == source_type]
        if source_id is not None:
            rows = [ref for ref in rows if ref.source_id == source_id]
        if workflow_run_id is not None:
            rows = [ref for ref in rows if ref.workflow_run_id == workflow_run_id]
        return list(rows)

    def _next_id(self, prefix: str) -> str:
        if prefix == "arun":
            value = self._next_agent_run_id
            self._next_agent_run_id += 1
        elif prefix == "arg":
            value = self._next_argument_id
            self._next_argument_id += 1
        elif prefix == "rsum":
            value = self._next_round_summary_id
            self._next_round_summary_id += 1
        elif prefix == "jdg":
            value = self._next_judgment_id
            self._next_judgment_id += 1
        elif prefix == "jtc":
            value = self._next_tool_call_id
            self._next_tool_call_id += 1
        else:
            raise ValueError(f"unknown id prefix: {prefix}")
        return f"{prefix}_{value:06d}"


def seed_demo_repository() -> InMemoryAgentSwarmRepository:
    repo = InMemoryAgentSwarmRepository()
    created_at = datetime(2026, 5, 13, 10, 1, tzinfo=UTC)
    workflow_run_id = "wr_20260513_002594_000001"
    agent_run = repo.start_agent_run(
        workflow_run_id=workflow_run_id,
        agent_id="bull_v1",
        role="bullish_interpreter",
        started_at=created_at,
    )
    argument = repo.save_argument(
        workflow_run_id=workflow_run_id,
        agent_run_id=agent_run.agent_run_id,
        draft=AgentArgumentDraft(
            agent_id="bull_v1",
            role="bullish_interpreter",
            round=1,
            argument="从多头视角看，盈利改善证据支持基本面改善 thesis，但现金流质量需要复核。",
            confidence=0.81,
            referenced_evidence_ids=("ev_20260513_002594_report_001",),
            counter_evidence_ids=("ev_20260513_002594_report_003",),
            limitations=("现金流质量和同业估值仍需核对",),
            role_output={
                "stance_interpretation": "盈利改善证据支持多头 thesis。",
                "bullish_impact_assessment": 0.72,
            },
        ),
        created_at=created_at,
    )
    repo.complete_agent_run(agent_run.agent_run_id, completed_at=created_at, rounds=(1,))
    repo.save_round_summary(
        RoundSummaryDraft(
            workflow_run_id=workflow_run_id,
            round=1,
            summary="第 1 轮形成盈利改善 thesis，同时保留现金流质量待核对。",
            participants=("bull_v1",),
            agent_argument_ids=(argument.agent_argument_id,),
            referenced_evidence_ids=("ev_20260513_002594_report_001",),
            disputed_evidence_ids=("ev_20260513_002594_report_003",),
        ),
        created_at=created_at,
    )
    judgment = JudgmentRecord(
        judgment_id="jdg_20260513_002594_001",
        workflow_run_id=workflow_run_id,
        final_signal="neutral",
        confidence=0.74,
        time_horizon="short_to_mid_term",
        key_positive_evidence_ids=("ev_20260513_002594_report_001",),
        key_negative_evidence_ids=("ev_20260513_002594_report_003",),
        reasoning="中期基本面有支撑，但现金流和估值仍需复核。",
        risk_notes=("现金流质量低于利润增速。",),
        suggested_next_checks=("补充最新同行横向估值对比",),
        referenced_agent_argument_ids=(argument.agent_argument_id,),
        limitations=("缺少最新同行横向估值对比",),
        created_at=datetime(2026, 5, 13, 10, 3, 42, tzinfo=UTC),
    )
    repo.save_judgment(judgment)
    repo.save_tool_call(
        JudgeToolCallRecord(
            tool_call_id="jtc_20260513_002594_001",
            judgment_id=judgment.judgment_id,
            tool_name="get_evidence_detail",
            input={"evidence_id": "ev_20260513_002594_report_001"},
            result_ref={
                "evidence_id": "ev_20260513_002594_report_001",
                "raw_ref": "raw_20260513_002594_report_001",
            },
            output_summary="source_quality=0.9，structuring_confidence=0.82。",
            referenced_evidence_ids=("ev_20260513_002594_report_001",),
            used_for="verify_profit_growth_claim",
            created_at=datetime(2026, 5, 13, 10, 2, 30, tzinfo=UTC),
        )
    )
    repo.save_references(
        [
            EvidenceReference(
                reference_id="eref_demo_arg_001",
                source_type="agent_argument",
                source_id=argument.agent_argument_id,
                evidence_id="ev_20260513_002594_report_001",
                reference_role="supports",
                round=1,
                workflow_run_id=workflow_run_id,
                created_at=created_at,
            ),
            EvidenceReference(
                reference_id="eref_demo_arg_002",
                source_type="agent_argument",
                source_id=argument.agent_argument_id,
                evidence_id="ev_20260513_002594_report_003",
                reference_role="counters",
                round=1,
                workflow_run_id=workflow_run_id,
                created_at=created_at,
            ),
            EvidenceReference(
                reference_id="eref_demo_jdg_001",
                source_type="judgment",
                source_id=judgment.judgment_id,
                evidence_id="ev_20260513_002594_report_001",
                reference_role="supports",
                workflow_run_id=workflow_run_id,
                created_at=judgment.created_at,
            ),
            EvidenceReference(
                reference_id="eref_demo_jdg_002",
                source_type="judgment",
                source_id=judgment.judgment_id,
                evidence_id="ev_20260513_002594_report_003",
                reference_role="counters",
                workflow_run_id=workflow_run_id,
                created_at=judgment.created_at,
            ),
        ]
    )
    return repo
