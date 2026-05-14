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
    AgentArgumentRecord,
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
from .config import (
    DEFAULT_DEBATE_WORKFLOW_CONFIGS,
    DebateAgentConfig,
    DebateWorkflowConfig,
    get_debate_workflow_config,
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
        workflow_configs: Mapping[str, DebateWorkflowConfig] | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.repository = repository or InMemoryAgentSwarmRepository()
        self.workflow_configs = workflow_configs or DEFAULT_DEBATE_WORKFLOW_CONFIGS

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
        workflow_config = get_debate_workflow_config(
            swarm_input.workflow_config_id,
            self.workflow_configs,
        )

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

        round_numbers = tuple(range(1, workflow_config.debate_rounds + 1))
        agent_runs = {
            agent.agent_id: self.repository.start_agent_run(
                workflow_run_id=swarm_input.workflow_run_id,
                agent_id=agent.agent_id,
                role=agent.role,
                started_at=accepted_at,
            )
            for agent in workflow_config.agents
        }
        saved_argument_ids: list[str] = []
        saved_summary_ids: list[str] = []

        for round_number in round_numbers:
            round_arguments = []
            for agent_config in workflow_config.agents:
                support_ids = _support_evidence_ids(details, round_number)
                counter_ids = _counter_evidence_ids(details, round_number)
                draft = _build_argument_draft(
                    agent_config=agent_config,
                    swarm_input=swarm_input,
                    details=details,
                    round_number=round_number,
                    total_rounds=workflow_config.debate_rounds,
                    support_ids=support_ids,
                    counter_ids=counter_ids,
                )
                argument = self.repository.save_argument(
                    workflow_run_id=swarm_input.workflow_run_id,
                    agent_run_id=agent_runs[agent_config.agent_id].agent_run_id,
                    draft=draft,
                    created_at=accepted_at,
                )
                round_arguments.append(argument)
                saved_argument_ids.append(argument.agent_argument_id)
                saved_argument_refs = self.evidence_store.save_references(
                    envelope,
                    EvidenceReferenceBatch(
                        source_type="agent_argument",
                        source_id=argument.agent_argument_id,
                        references=_reference_payloads(
                            argument.referenced_evidence_ids,
                            argument.counter_evidence_ids,
                            round_number,
                        ),
                    ),
                )
                self.repository.save_references(saved_argument_refs.accepted_references)

            summary = self.repository.save_round_summary(
                RoundSummaryDraft(
                    workflow_run_id=swarm_input.workflow_run_id,
                    round=round_number,
                    summary=_round_summary_text(
                        round_number=round_number,
                        total_rounds=workflow_config.debate_rounds,
                        arguments=round_arguments,
                    ),
                    participants=tuple(argument.agent_id for argument in round_arguments),
                    agent_argument_ids=tuple(
                        argument.agent_argument_id for argument in round_arguments
                    ),
                    referenced_evidence_ids=_unique_ids(
                        evidence_id
                        for argument in round_arguments
                        for evidence_id in argument.referenced_evidence_ids
                    ),
                    disputed_evidence_ids=_unique_ids(
                        evidence_id
                        for argument in round_arguments
                        for evidence_id in argument.counter_evidence_ids
                    ),
                ),
                created_at=accepted_at,
            )
            saved_summary_ids.append(summary.round_summary_id)
            saved_summary_refs = self.evidence_store.save_references(
                envelope,
                EvidenceReferenceBatch(
                    source_type="round_summary",
                    source_id=summary.round_summary_id,
                    references=_reference_payloads(
                        summary.referenced_evidence_ids,
                        summary.disputed_evidence_ids,
                        round_number,
                    ),
                ),
            )
            self.repository.save_references(saved_summary_refs.accepted_references)

        for agent_run in agent_runs.values():
            self.repository.complete_agent_run(
                agent_run.agent_run_id,
                completed_at=accepted_at,
                rounds=round_numbers,
            )

        return AgentSwarmRunOutcome(
            task_id=task_id,
            status="completed",
            accepted_at=accepted_at,
            agent_argument_ids=tuple(saved_argument_ids),
            round_summary_id=saved_summary_ids[-1] if saved_summary_ids else None,
            round_summary_ids=tuple(saved_summary_ids),
        )


def _build_argument_draft(
    *,
    agent_config: DebateAgentConfig,
    swarm_input: AgentSwarmInput,
    details: list[Any],
    round_number: int,
    total_rounds: int,
    support_ids: tuple[str, ...],
    counter_ids: tuple[str, ...],
) -> AgentArgumentDraft:
    evidence_titles = _evidence_titles(details, support_ids, counter_ids)
    argument_text = (
        f"第 {round_number}/{total_rounds} 轮，{agent_config.agent_id} 从 "
        f"{agent_config.stance_label} 视角复核 {swarm_input.ticker}："
        f"已入库证据支持 {agent_config.thesis_label}；"
        f"核心材料包括：{'、'.join(evidence_titles)}。"
    )
    if round_number > 1:
        argument_text += " 本轮基于上一轮摘要继续压缩论点，并检查是否存在相反 Evidence。"
    if counter_ids:
        argument_text += " 同时存在反向或待核对 Evidence，需要 Judge 保留限制条件。"

    confidence = _round_confidence(details, round_number)
    return AgentArgumentDraft(
        agent_id=agent_config.agent_id,
        role=agent_config.role,
        round=round_number,
        argument=argument_text,
        confidence=confidence,
        referenced_evidence_ids=support_ids,
        counter_evidence_ids=counter_ids,
        limitations=(agent_config.limitation,),
        role_output={
            agent_config.stance_output_key: (
                "证据整体支持当前 thesis，但结论必须通过 Evidence Reference 回查。"
            ),
            agent_config.impact_output_key: round(max(0.0, confidence - 0.08), 2),
            "round": round_number,
            "total_rounds": total_rounds,
        },
    )


def _support_evidence_ids(details: list[Any], round_number: int) -> tuple[str, ...]:
    if len(details) <= 2:
        return tuple(detail.evidence.evidence_id for detail in details)
    start = (round_number - 1) % len(details)
    ordered = [details[(start + offset) % len(details)] for offset in range(len(details))]
    support = [detail.evidence.evidence_id for detail in ordered[:2]]
    return tuple(support)


def _counter_evidence_ids(details: list[Any], round_number: int) -> tuple[str, ...]:
    if len(details) <= 2:
        return ()
    counter_index = (round_number + 1) % len(details)
    counter_id = details[counter_index].evidence.evidence_id
    support_ids = set(_support_evidence_ids(details, round_number))
    if counter_id in support_ids:
        return ()
    return (counter_id,)


def _reference_payloads(
    support_ids: tuple[str, ...],
    counter_ids: tuple[str, ...],
    round_number: int,
) -> list[dict[str, Any]]:
    return [
        *[
            {"evidence_id": evidence_id, "reference_role": "supports", "round": round_number}
            for evidence_id in support_ids
        ],
        *[
            {"evidence_id": evidence_id, "reference_role": "counters", "round": round_number}
            for evidence_id in counter_ids
        ],
    ]


def _round_summary_text(
    *,
    round_number: int,
    total_rounds: int,
    arguments: list[AgentArgumentRecord],
) -> str:
    participants = "、".join(argument.agent_id for argument in arguments)
    referenced_count = len(
        _unique_ids(
            evidence_id
            for argument in arguments
            for evidence_id in argument.referenced_evidence_ids
        )
    )
    disputed_count = len(
        _unique_ids(
            evidence_id
            for argument in arguments
            for evidence_id in argument.counter_evidence_ids
        )
    )
    summary = (
        f"第 {round_number}/{total_rounds} 轮由 {participants} 完成论证压缩，"
        f"保留 {referenced_count} 条支持 Evidence。"
    )
    if disputed_count:
        summary += f" 同时标记 {disputed_count} 条反向或待核对 Evidence。"
    else:
        summary += " 未发现单独的反向 Evidence。"
    return summary


def _evidence_titles(
    details: list[Any],
    support_ids: tuple[str, ...],
    counter_ids: tuple[str, ...],
) -> list[str]:
    wanted = [*support_ids, *counter_ids]
    by_id = {detail.evidence.evidence_id: detail.evidence for detail in details}
    return [
        by_id[evidence_id].title or evidence_id
        for evidence_id in wanted
        if evidence_id in by_id
    ]


def _unique_ids(values: Any) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


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


def _round_confidence(details: list[Any], round_number: int) -> float:
    confidence = _agent_confidence(details) - min(round_number - 1, 4) * 0.01
    return round(max(0.55, min(0.88, confidence)), 2)


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
