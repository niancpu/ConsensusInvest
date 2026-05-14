"""Deterministic MVP Agent Swarm and Judge Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from consensusinvest.evidence_store import (
    EvidenceReferenceBatch,
    EvidenceStoreClient,
)
from consensusinvest.runtime import InternalCallEnvelope

from .models import (
    AgentArgumentDraft,
    AgentSwarmHistory,
    AgentSwarmInput,
    AgentSwarmRunOutcome,
    EvidenceGap,
    EvidenceSelection,
    JudgeInput,
    JudgeRunOutcome,
    JudgeToolAccess,
    JudgeToolCallRecord,
    JudgmentRecord,
    RoundSummaryDraft,
    SuggestedSearch,
)
from .repository import InMemoryAgentSwarmRepository

_T = TypeVar("_T")


class AgentSwarmRuntime:
    """Runs configured debate agents over already-ingested Evidence."""

    def __init__(
        self,
        *,
        evidence_store: EvidenceStoreClient,
        repository: InMemoryAgentSwarmRepository | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.repository = repository or InMemoryAgentSwarmRepository()

    def run(
        self,
        envelope: InternalCallEnvelope,
        input: AgentSwarmInput | Mapping[str, Any],
    ) -> AgentSwarmRunOutcome:
        envelope.validate_for_create()
        swarm_input = _coerce_agent_swarm_input(input)
        _validate_workflow_scope(envelope, swarm_input.workflow_run_id)
        accepted_at = _timestamp(envelope)
        task_id = f"aswarm_{accepted_at.strftime('%Y%m%d_%H%M%S')}_{swarm_input.ticker}"

        if not swarm_input.evidence_selection.evidence_ids:
            return AgentSwarmRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=(_default_gap(swarm_input),),
            )

        details = []
        missing_ids = []
        for evidence_id in swarm_input.evidence_selection.evidence_ids:
            try:
                details.append(self.evidence_store.get_evidence(envelope, evidence_id))
            except KeyError:
                missing_ids.append(evidence_id)

        if missing_ids:
            return AgentSwarmRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=(
                    EvidenceGap(
                        gap_type="missing_evidence_ids",
                        description=f"Evidence Store 中缺少请求的 Evidence: {', '.join(missing_ids)}。",
                        suggested_search=_suggested_search(swarm_input),
                    ),
                ),
            )

        support_ids = tuple(detail.evidence.evidence_id for detail in details[:2])
        counter_ids = tuple(detail.evidence.evidence_id for detail in details[2:3])
        evidence_titles = [detail.evidence.title or detail.evidence.evidence_id for detail in details[:3]]
        argument_text = (
            "从多头视角看，已入库证据支持基本面改善 thesis；"
            f"核心材料包括：{'、'.join(evidence_titles)}。"
        )
        if counter_ids:
            argument_text += " 同时存在反向或待核对 Evidence，需要 Judge 保留限制条件。"

        agent_run = self.repository.start_agent_run(
            workflow_run_id=swarm_input.workflow_run_id,
            agent_id="bull_v1",
            role="bullish_interpreter",
            started_at=accepted_at,
        )
        draft = AgentArgumentDraft(
            agent_id="bull_v1",
            role="bullish_interpreter",
            round=1,
            argument=argument_text,
            confidence=_agent_confidence(details),
            referenced_evidence_ids=support_ids,
            counter_evidence_ids=counter_ids,
            limitations=("未覆盖完整同业对比和估值敏感性。",),
            role_output={
                "stance_interpretation": "证据整体支持多头 thesis，但仍需保留风险限制。",
                "bullish_impact_assessment": round(_agent_confidence(details) - 0.08, 2),
            },
        )
        argument = self.repository.save_argument(
            workflow_run_id=swarm_input.workflow_run_id,
            agent_run_id=agent_run.agent_run_id,
            draft=draft,
            created_at=accepted_at,
        )
        self.repository.complete_agent_run(agent_run.agent_run_id, completed_at=accepted_at, rounds=(1,))
        saved_argument_refs = self.evidence_store.save_references(
            envelope,
            EvidenceReferenceBatch(
                source_type="agent_argument",
                source_id=argument.agent_argument_id,
                references=[
                    *[
                        {"evidence_id": evidence_id, "reference_role": "supports", "round": 1}
                        for evidence_id in argument.referenced_evidence_ids
                    ],
                    *[
                        {"evidence_id": evidence_id, "reference_role": "counters", "round": 1}
                        for evidence_id in argument.counter_evidence_ids
                    ],
                ],
            ),
        )
        self.repository.save_references(saved_argument_refs.accepted_references)

        summary = self.repository.save_round_summary(
            RoundSummaryDraft(
                workflow_run_id=swarm_input.workflow_run_id,
                round=1,
                summary="第 1 轮形成多头 thesis，并保留反向 Evidence 与数据缺口供 Judge 复核。",
                participants=("bull_v1",),
                agent_argument_ids=(argument.agent_argument_id,),
                referenced_evidence_ids=argument.referenced_evidence_ids,
                disputed_evidence_ids=argument.counter_evidence_ids,
            ),
            created_at=accepted_at,
        )
        saved_summary_refs = self.evidence_store.save_references(
            envelope,
            EvidenceReferenceBatch(
                source_type="round_summary",
                source_id=summary.round_summary_id,
                references=[
                    *[
                        {"evidence_id": evidence_id, "reference_role": "supports", "round": 1}
                        for evidence_id in summary.referenced_evidence_ids
                    ],
                    *[
                        {"evidence_id": evidence_id, "reference_role": "counters", "round": 1}
                        for evidence_id in summary.disputed_evidence_ids
                    ],
                ],
            ),
        )
        self.repository.save_references(saved_summary_refs.accepted_references)

        return AgentSwarmRunOutcome(
            task_id=task_id,
            status="completed",
            accepted_at=accepted_at,
            agent_argument_ids=(argument.agent_argument_id,),
            round_summary_id=summary.round_summary_id,
        )


class JudgeRuntime:
    """Produces final workflow judgment from saved arguments and Evidence."""

    def __init__(
        self,
        *,
        evidence_store: EvidenceStoreClient,
        repository: InMemoryAgentSwarmRepository,
    ) -> None:
        self.evidence_store = evidence_store
        self.repository = repository

    def run(
        self,
        envelope: InternalCallEnvelope,
        input: JudgeInput | Mapping[str, Any],
    ) -> JudgeRunOutcome:
        envelope.validate_for_create()
        judge_input = _coerce_judge_input(input)
        _validate_workflow_scope(envelope, judge_input.workflow_run_id)
        accepted_at = _timestamp(envelope)
        task_id = f"judge_{accepted_at.strftime('%Y%m%d_%H%M%S')}"
        if not judge_input.agent_argument_ids or not judge_input.key_evidence_ids:
            return JudgeRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=(
                    EvidenceGap(
                        gap_type="missing_judge_inputs",
                        description="Judge 缺少 Agent Argument 或 key Evidence，不能形成完整判断。",
                    ),
                ),
            )

        arguments = [
            self.repository.get_argument(argument_id)
            for argument_id in judge_input.agent_argument_ids
        ]
        arguments = [argument for argument in arguments if argument is not None]
        if not arguments:
            return JudgeRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=(
                    EvidenceGap(
                        gap_type="missing_agent_arguments",
                        description="Judge 请求的 Agent Argument 尚未保存。",
                    ),
                ),
            )

        details = []
        for evidence_id in judge_input.key_evidence_ids:
            try:
                details.append(self.evidence_store.get_evidence(envelope, evidence_id))
            except KeyError:
                return JudgeRunOutcome(
                    task_id=task_id,
                    status="insufficient_evidence",
                    accepted_at=accepted_at,
                    gaps=(
                        EvidenceGap(
                            gap_type="missing_evidence_ids",
                            description=f"Judge 请求的 Evidence 不存在：{evidence_id}。",
                        ),
                    ),
                )

        positive_ids = tuple(detail.evidence.evidence_id for detail in details[:1])
        negative_ids = tuple(detail.evidence.evidence_id for detail in details[1:2])
        final_signal = "neutral" if negative_ids else "bullish"
        judgment = JudgmentRecord(
            judgment_id=self.repository.new_judgment_id(),
            workflow_run_id=judge_input.workflow_run_id,
            final_signal=final_signal,
            confidence=0.74 if negative_ids else 0.78,
            time_horizon="short_to_mid_term",
            key_positive_evidence_ids=positive_ids,
            key_negative_evidence_ids=negative_ids,
            reasoning="基于已保存 Agent Argument 和 key Evidence，基本面支持 thesis 仍需与风险项共同评估。",
            risk_notes=("反向 Evidence 或缺口会压低最终信号置信度。",) if negative_ids else (),
            suggested_next_checks=("补充最新同业横向估值对比",),
            referenced_agent_argument_ids=tuple(argument.agent_argument_id for argument in arguments),
            limitations=("Judge 未直接触发搜索，缺口需交由 Orchestrator 判断是否补齐。",),
            created_at=accepted_at,
        )
        self.repository.save_judgment(judgment)

        for detail in details:
            if judge_input.tool_access.get_evidence_detail:
                call = JudgeToolCallRecord(
                    tool_call_id=self.repository.new_tool_call_id(),
                    judgment_id=judgment.judgment_id,
                    tool_name="get_evidence_detail",
                    input={"evidence_id": detail.evidence.evidence_id},
                    result_ref={
                        "evidence_id": detail.evidence.evidence_id,
                        "raw_ref": detail.raw_ref,
                    },
                    output_summary=(
                        f"source_quality={detail.evidence.source_quality}，"
                        f"structuring_confidence={getattr(detail.structure, 'structuring_confidence', None)}。"
                    ),
                    referenced_evidence_ids=(detail.evidence.evidence_id,),
                    used_for="verify_key_evidence",
                    created_at=accepted_at,
                )
                self.repository.save_tool_call(call)

        saved_refs = self.evidence_store.save_references(
            envelope,
            EvidenceReferenceBatch(
                source_type="judgment",
                source_id=judgment.judgment_id,
                references=[
                    *[
                        {"evidence_id": evidence_id, "reference_role": "supports"}
                        for evidence_id in judgment.key_positive_evidence_ids
                    ],
                    *[
                        {"evidence_id": evidence_id, "reference_role": "counters"}
                        for evidence_id in judgment.key_negative_evidence_ids
                    ],
                ],
            ),
        )
        self.repository.save_references(saved_refs.accepted_references)
        return JudgeRunOutcome(
            task_id=task_id,
            status="completed",
            accepted_at=accepted_at,
            judgment_id=judgment.judgment_id,
        )


def _validate_workflow_scope(envelope: InternalCallEnvelope, workflow_run_id: str) -> None:
    if envelope.workflow_run_id != workflow_run_id:
        raise ValueError("workflow_run_id must match envelope.workflow_run_id")


def _timestamp(envelope: InternalCallEnvelope) -> datetime:
    return envelope.analysis_time or datetime.now(UTC)


def _agent_confidence(details: list[Any]) -> float:
    qualities = [
        detail.evidence.source_quality
        for detail in details
        if detail.evidence.source_quality is not None
    ]
    if not qualities:
        return 0.62
    return round(max(0.55, min(0.88, sum(qualities) / len(qualities))), 2)


def _default_gap(swarm_input: AgentSwarmInput) -> EvidenceGap:
    return EvidenceGap(
        gap_type="missing_core_evidence",
        description="缺少可供 Agent Swarm 论证的已入库 Evidence。",
        suggested_search=_suggested_search(swarm_input),
    )


def _suggested_search(swarm_input: AgentSwarmInput) -> SuggestedSearch:
    return SuggestedSearch(
        target_entity_ids=(swarm_input.entity_id,) if swarm_input.entity_id else (),
        evidence_types=("financial_report", "company_news", "industry_news"),
        lookback_days=365,
        keywords=(swarm_input.ticker, "基本面", "现金流", "同业 对比"),
    )


def _coerce_agent_swarm_input(value: AgentSwarmInput | Mapping[str, Any]) -> AgentSwarmInput:
    if isinstance(value, AgentSwarmInput):
        return value
    data = dict(value)
    selection = data.get("evidence_selection") or {}
    history = data.get("history") or {}
    data["evidence_selection"] = _coerce_dataclass(EvidenceSelection, selection)
    data["history"] = _coerce_dataclass(AgentSwarmHistory, history)
    return _coerce_dataclass(AgentSwarmInput, data)


def _coerce_judge_input(value: JudgeInput | Mapping[str, Any]) -> JudgeInput:
    if isinstance(value, JudgeInput):
        return value
    data = dict(value)
    tool_access = data.get("tool_access") or {}
    data["tool_access"] = _coerce_dataclass(JudgeToolAccess, tool_access)
    return _coerce_dataclass(JudgeInput, data)


def _coerce_dataclass(cls: type[_T], value: Any) -> _T:
    if isinstance(value, cls):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return value  # type: ignore[return-value]
    data = dict(value or {})
    allowed = {field.name for field in fields(cls)}
    return cls(**{key: data[key] for key in allowed if key in data})
