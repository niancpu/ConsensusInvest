"""Agent Swarm and Judge Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from consensusinvest.evidence_store import (
    EvidenceReferenceBatch,
    EvidenceStoreClient,
)
from consensusinvest.runtime import InternalCallEnvelope, RuntimeEvent

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
    RoundSummaryRecord,
    SuggestedSearch,
)
from .config import (
    DEFAULT_DEBATE_WORKFLOW_CONFIGS,
    DebateAgentConfig,
    DebateWorkflowConfig,
    get_debate_workflow_config,
)
from .llm import AgentLLMProvider
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
        llm_provider: AgentLLMProvider | None = None,
        runtime_event_repository: Any | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.repository = repository or InMemoryAgentSwarmRepository()
        self.workflow_configs = workflow_configs or DEFAULT_DEBATE_WORKFLOW_CONFIGS
        self.llm_provider = llm_provider
        self.runtime_event_repository = runtime_event_repository

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
        _append_runtime_event(
            self.runtime_event_repository,
            envelope=envelope,
            event_type="started",
            occurred_at=accepted_at,
            producer="agent_swarm",
            payload={
                "runtime": "agent_swarm",
                "task_id": task_id,
                "workflow_run_id": swarm_input.workflow_run_id,
                "workflow_config_id": swarm_input.workflow_config_id,
                "ticker": swarm_input.ticker,
                "status": "running",
                "evidence_count": len(swarm_input.evidence_selection.evidence_ids),
                "agent_count": len(workflow_config.agents),
                "debate_rounds": workflow_config.debate_rounds,
                "previous_judgment_count": len(swarm_input.history.previous_judgment_ids),
            },
        )

        if not swarm_input.evidence_selection.evidence_ids:
            gaps = (_default_gap(swarm_input),)
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="failed",
                occurred_at=accepted_at,
                producer="agent_swarm",
                payload={
                    "runtime": "agent_swarm",
                    "task_id": task_id,
                    "workflow_run_id": swarm_input.workflow_run_id,
                    "status": "insufficient_evidence",
                    "error_code": "insufficient_evidence",
                    "gap_types": _gap_types(gaps),
                    "gap_count": len(gaps),
                    "evidence_count": 0,
                },
            )
            return AgentSwarmRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=gaps,
            )

        details = []
        missing_ids = []
        for evidence_id in swarm_input.evidence_selection.evidence_ids:
            try:
                details.append(self.evidence_store.get_evidence(envelope, evidence_id))
            except KeyError:
                missing_ids.append(evidence_id)

        if missing_ids:
            gaps = (
                EvidenceGap(
                    gap_type="missing_evidence_ids",
                    description=f"Evidence Store 中缺少请求的 Evidence: {', '.join(missing_ids)}。",
                    suggested_search=_suggested_search(swarm_input),
                ),
            )
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="failed",
                occurred_at=accepted_at,
                producer="agent_swarm",
                payload={
                    "runtime": "agent_swarm",
                    "task_id": task_id,
                    "workflow_run_id": swarm_input.workflow_run_id,
                    "status": "insufficient_evidence",
                    "error_code": "insufficient_evidence",
                    "gap_types": _gap_types(gaps),
                    "gap_count": len(gaps),
                    "missing_evidence_ids": list(missing_ids),
                },
            )
            return AgentSwarmRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=gaps,
            )

        round_numbers = tuple(range(1, workflow_config.debate_rounds + 1))
        agent_runs = {}
        for agent in workflow_config.agents:
            agent_run = self.repository.start_agent_run(
                workflow_run_id=swarm_input.workflow_run_id,
                agent_id=agent.agent_id,
                role=agent.role,
                started_at=accepted_at,
            )
            agent_runs[agent.agent_id] = agent_run
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="started",
                occurred_at=accepted_at,
                producer="agent_swarm",
                payload={
                    "runtime": "agent_swarm",
                    "task_id": task_id,
                    "workflow_run_id": swarm_input.workflow_run_id,
                    "agent_run_id": agent_run.agent_run_id,
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "status": agent_run.status,
                },
            )
        saved_argument_ids: list[str] = []
        saved_summary_ids: list[str] = []

        for round_number in round_numbers:
            round_arguments = []
            for agent_config in workflow_config.agents:
                support_ids = _support_evidence_ids(details, round_number)
                counter_ids = _counter_evidence_ids(details, round_number)
                if self.llm_provider is not None:
                    draft = _build_llm_argument_draft(
                        self.llm_provider,
                        agent_config=agent_config,
                        swarm_input=swarm_input,
                        details=details,
                        round_number=round_number,
                        total_rounds=workflow_config.debate_rounds,
                        support_ids=support_ids,
                        counter_ids=counter_ids,
                    )
                else:
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
                _append_runtime_event(
                    self.runtime_event_repository,
                    envelope=envelope,
                    event_type="status_changed",
                    occurred_at=accepted_at,
                    producer="agent_swarm",
                    payload={
                        "runtime": "agent_swarm",
                        "task_id": task_id,
                        "workflow_run_id": swarm_input.workflow_run_id,
                        "agent_run_id": argument.agent_run_id,
                        "agent_id": argument.agent_id,
                        "status": "running",
                        "round": argument.round,
                        "agent_argument_id": argument.agent_argument_id,
                        "referenced_evidence_ids": list(argument.referenced_evidence_ids),
                        "counter_evidence_ids": list(argument.counter_evidence_ids),
                        "referenced_evidence_count": len(argument.referenced_evidence_ids),
                        "counter_evidence_count": len(argument.counter_evidence_ids),
                    },
                )
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

            summary_draft = _build_round_summary_draft(
                llm_provider=self.llm_provider,
                workflow_run_id=swarm_input.workflow_run_id,
                round_number=round_number,
                total_rounds=workflow_config.debate_rounds,
                arguments=round_arguments,
            )
            summary = self.repository.save_round_summary(
                summary_draft,
                created_at=accepted_at,
            )
            saved_summary_ids.append(summary.round_summary_id)
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="status_changed",
                occurred_at=accepted_at,
                producer="agent_swarm",
                payload={
                    "runtime": "agent_swarm",
                    "task_id": task_id,
                    "workflow_run_id": swarm_input.workflow_run_id,
                    "status": "running",
                    "round": summary.round,
                    "round_summary_id": summary.round_summary_id,
                    "agent_argument_ids": list(summary.agent_argument_ids),
                    "referenced_evidence_ids": list(summary.referenced_evidence_ids),
                    "disputed_evidence_ids": list(summary.disputed_evidence_ids),
                },
            )
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
            completed_agent_run = self.repository.complete_agent_run(
                agent_run.agent_run_id,
                completed_at=accepted_at,
                rounds=round_numbers,
            )
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="completed",
                occurred_at=accepted_at,
                producer="agent_swarm",
                payload={
                    "runtime": "agent_swarm",
                    "task_id": task_id,
                    "workflow_run_id": swarm_input.workflow_run_id,
                    "agent_run_id": completed_agent_run.agent_run_id,
                    "agent_id": completed_agent_run.agent_id,
                    "status": completed_agent_run.status,
                    "rounds": list(completed_agent_run.rounds),
                },
            )

        _append_runtime_event(
            self.runtime_event_repository,
            envelope=envelope,
            event_type="completed",
            occurred_at=accepted_at,
            producer="agent_swarm",
            payload={
                "runtime": "agent_swarm",
                "task_id": task_id,
                "workflow_run_id": swarm_input.workflow_run_id,
                "status": "completed",
                "agent_run_ids": [run.agent_run_id for run in agent_runs.values()],
                "agent_argument_ids": list(saved_argument_ids),
                "round_summary_ids": list(saved_summary_ids),
                "agent_argument_count": len(saved_argument_ids),
                "round_summary_count": len(saved_summary_ids),
            },
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


def _build_llm_argument_draft(
    llm_provider: AgentLLMProvider,
    *,
    agent_config: DebateAgentConfig,
    swarm_input: AgentSwarmInput,
    details: list[Any],
    round_number: int,
    total_rounds: int,
    support_ids: tuple[str, ...],
    counter_ids: tuple[str, ...],
) -> AgentArgumentDraft:
    allowed_ids = tuple(detail.evidence.evidence_id for detail in details)
    payload = {
        "task": "build_agent_argument",
        "output_schema": {
            "argument": "string",
            "confidence": "number between 0 and 1",
            "referenced_evidence_ids": ["evidence_id from allowed_evidence_ids"],
            "counter_evidence_ids": ["evidence_id from allowed_evidence_ids"],
            "limitations": ["string"],
            "role_output": "object",
        },
        "workflow": {
            "workflow_run_id": swarm_input.workflow_run_id,
            "ticker": swarm_input.ticker,
            "entity_id": swarm_input.entity_id,
            "round": round_number,
            "total_rounds": total_rounds,
        },
        "agent": {
            "agent_id": agent_config.agent_id,
            "role": agent_config.role,
            "stance_label": agent_config.stance_label,
            "thesis_label": agent_config.thesis_label,
            "stance_output_key": agent_config.stance_output_key,
            "impact_output_key": agent_config.impact_output_key,
            "default_limitation": agent_config.limitation,
        },
        "allowed_evidence_ids": list(allowed_ids),
        "preferred_support_ids": list(support_ids),
        "preferred_counter_ids": list(counter_ids),
        "evidence": _llm_evidence_payload(details),
    }
    raw = llm_provider.complete_json(
        purpose="agent_argument",
        system_prompt=_AGENT_ARGUMENT_SYSTEM_PROMPT,
        user_payload=payload,
    )
    references = _filter_ids(_clean_sequence(raw.get("referenced_evidence_ids")), allowed_ids)
    counters = _filter_ids(_clean_sequence(raw.get("counter_evidence_ids")), allowed_ids)
    if not references:
        references = support_ids
    limitations = tuple(_clean_sequence(raw.get("limitations"))) or (agent_config.limitation,)
    role_output = raw.get("role_output")
    if not isinstance(role_output, Mapping):
        role_output = {}
    role_output = dict(role_output)
    role_output.setdefault("llm_provider", "litellm")
    role_output.setdefault("round", round_number)
    role_output.setdefault("total_rounds", total_rounds)
    return AgentArgumentDraft(
        agent_id=agent_config.agent_id,
        role=agent_config.role,
        round=round_number,
        argument=_clean_key_value(raw.get("argument"))
        or _build_argument_draft(
            agent_config=agent_config,
            swarm_input=swarm_input,
            details=details,
            round_number=round_number,
            total_rounds=total_rounds,
            support_ids=references,
            counter_ids=counters,
        ).argument,
        confidence=_bounded_float(raw.get("confidence"), default=_round_confidence(details, round_number)),
        referenced_evidence_ids=references,
        counter_evidence_ids=counters,
        limitations=limitations,
        role_output=role_output,
    )


def _build_round_summary_draft(
    *,
    llm_provider: AgentLLMProvider | None,
    workflow_run_id: str,
    round_number: int,
    total_rounds: int,
    arguments: list[AgentArgumentRecord],
) -> RoundSummaryDraft:
    referenced_ids = _unique_ids(
        evidence_id for argument in arguments for evidence_id in argument.referenced_evidence_ids
    )
    disputed_ids = _unique_ids(
        evidence_id for argument in arguments for evidence_id in argument.counter_evidence_ids
    )
    argument_ids = tuple(argument.agent_argument_id for argument in arguments)
    participants = tuple(argument.agent_id for argument in arguments)
    summary_text = _round_summary_text(
        round_number=round_number,
        total_rounds=total_rounds,
        arguments=arguments,
    )
    if llm_provider is not None:
        raw = llm_provider.complete_json(
            purpose="round_summary",
            system_prompt=_ROUND_SUMMARY_SYSTEM_PROMPT,
            user_payload={
                "task": "build_round_summary",
                "output_schema": {"summary": "string"},
                "workflow_run_id": workflow_run_id,
                "round": round_number,
                "total_rounds": total_rounds,
                "agent_argument_ids": list(argument_ids),
                "arguments": [
                    {
                        "agent_argument_id": argument.agent_argument_id,
                        "agent_id": argument.agent_id,
                        "role": argument.role,
                        "argument": argument.argument,
                        "confidence": argument.confidence,
                        "referenced_evidence_ids": list(argument.referenced_evidence_ids),
                        "counter_evidence_ids": list(argument.counter_evidence_ids),
                        "limitations": list(argument.limitations),
                    }
                    for argument in arguments
                ],
            },
        )
        summary_text = _clean_key_value(raw.get("summary")) or summary_text
    return RoundSummaryDraft(
        workflow_run_id=workflow_run_id,
        round=round_number,
        summary=summary_text,
        participants=participants,
        agent_argument_ids=argument_ids,
        referenced_evidence_ids=referenced_ids,
        disputed_evidence_ids=disputed_ids,
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


def _build_judgment_record(
    *,
    repository: InMemoryAgentSwarmRepository,
    llm_provider: AgentLLMProvider | None,
    judge_input: JudgeInput,
    arguments: list[AgentArgumentRecord],
    summaries: list[RoundSummaryRecord],
    details: list[Any],
    created_at: datetime,
) -> JudgmentRecord:
    positive_ids = tuple(detail.evidence.evidence_id for detail in details[:1])
    negative_ids = tuple(detail.evidence.evidence_id for detail in details[1:2])
    argument_ids = tuple(argument.agent_argument_id for argument in arguments)
    summary_limitations = _summary_limitations(summaries, argument_ids)
    if llm_provider is None:
        final_signal = "neutral" if negative_ids else "bullish"
        return JudgmentRecord(
            judgment_id=repository.new_judgment_id(),
            workflow_run_id=judge_input.workflow_run_id,
            final_signal=final_signal,
            confidence=0.74 if negative_ids else 0.78,
            time_horizon="short_to_mid_term",
            key_positive_evidence_ids=positive_ids,
            key_negative_evidence_ids=negative_ids,
            reasoning=(
                "基于已保存 Round Summary、Agent Argument 和 key Evidence，"
                "基本面支持 thesis 仍需与风险项共同评估。"
            ),
            risk_notes=("反向 Evidence 或缺口会压低最终信号置信度。",) if negative_ids else (),
            suggested_next_checks=("补充最新同业横向估值对比",),
            referenced_agent_argument_ids=argument_ids,
            limitations=(
                "Judge 未直接触发搜索，缺口需交由 Orchestrator 判断是否补齐。",
                *summary_limitations,
            ),
            created_at=created_at,
        )

    allowed_evidence_ids = tuple(detail.evidence.evidence_id for detail in details)
    summary_ids = tuple(summary.round_summary_id for summary in summaries)
    raw = llm_provider.complete_json(
        purpose="judge",
        system_prompt=_JUDGE_SYSTEM_PROMPT,
        user_payload={
            "task": "build_judgment",
            "output_schema": {
                "final_signal": "bullish|bearish|neutral|insufficient_evidence",
                "confidence": "number between 0 and 1",
                "time_horizon": "string",
                "key_positive_evidence_ids": ["evidence_id from allowed_evidence_ids"],
                "key_negative_evidence_ids": ["evidence_id from allowed_evidence_ids"],
                "reasoning": "string",
                "risk_notes": ["string"],
                "suggested_next_checks": ["string"],
                "referenced_agent_argument_ids": ["id from allowed_agent_argument_ids"],
                "limitations": ["string"],
            },
            "workflow_run_id": judge_input.workflow_run_id,
            "round_summary_ids": list(summary_ids),
            "allowed_evidence_ids": list(allowed_evidence_ids),
            "allowed_agent_argument_ids": list(argument_ids),
            "round_summaries": [
                {
                    "round_summary_id": summary.round_summary_id,
                    "round": summary.round,
                    "summary": summary.summary,
                    "participants": list(summary.participants),
                    "agent_argument_ids": list(summary.agent_argument_ids),
                    "referenced_evidence_ids": list(summary.referenced_evidence_ids),
                    "disputed_evidence_ids": list(summary.disputed_evidence_ids),
                }
                for summary in summaries
            ],
            "arguments": [
                {
                    "agent_argument_id": argument.agent_argument_id,
                    "agent_id": argument.agent_id,
                    "role": argument.role,
                    "round": argument.round,
                    "argument": argument.argument,
                    "confidence": argument.confidence,
                    "referenced_evidence_ids": list(argument.referenced_evidence_ids),
                    "counter_evidence_ids": list(argument.counter_evidence_ids),
                    "limitations": list(argument.limitations),
                }
                for argument in arguments
            ],
            "evidence": _llm_evidence_payload(details),
        },
    )
    llm_positive = _filter_ids(_clean_sequence(raw.get("key_positive_evidence_ids")), allowed_evidence_ids)
    llm_negative = _filter_ids(_clean_sequence(raw.get("key_negative_evidence_ids")), allowed_evidence_ids)
    llm_argument_ids = _filter_ids(_clean_sequence(raw.get("referenced_agent_argument_ids")), argument_ids)
    final_signal = _clean_key_value(raw.get("final_signal")) or ("neutral" if negative_ids else "bullish")
    if final_signal not in {"bullish", "bearish", "neutral", "insufficient_evidence"}:
        final_signal = "neutral"
    return JudgmentRecord(
        judgment_id=repository.new_judgment_id(),
        workflow_run_id=judge_input.workflow_run_id,
        final_signal=final_signal,
        confidence=_bounded_float(raw.get("confidence"), default=0.74),
        time_horizon=_clean_key_value(raw.get("time_horizon")) or "short_to_mid_term",
        key_positive_evidence_ids=llm_positive or positive_ids,
        key_negative_evidence_ids=llm_negative or negative_ids,
        reasoning=_clean_key_value(raw.get("reasoning"))
        or "基于已保存 Agent Argument 和 key Evidence 形成判断。",
        risk_notes=tuple(_clean_sequence(raw.get("risk_notes"))),
        suggested_next_checks=tuple(_clean_sequence(raw.get("suggested_next_checks"))),
        referenced_agent_argument_ids=llm_argument_ids or argument_ids,
        limitations=tuple(_clean_sequence(raw.get("limitations")))
        or (
            "Judge 未直接触发搜索，缺口需交由 Orchestrator 判断是否补齐。",
            *summary_limitations,
        ),
        created_at=created_at,
    )


class JudgeRuntime:
    """Produces final workflow judgment from saved arguments and Evidence."""

    def __init__(
        self,
        *,
        evidence_store: EvidenceStoreClient,
        repository: InMemoryAgentSwarmRepository,
        llm_provider: AgentLLMProvider | None = None,
        runtime_event_repository: Any | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.repository = repository
        self.llm_provider = llm_provider
        self.runtime_event_repository = runtime_event_repository

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
        _append_runtime_event(
            self.runtime_event_repository,
            envelope=envelope,
            event_type="started",
            occurred_at=accepted_at,
            producer="judge_runtime",
            payload={
                "runtime": "judge",
                "task_id": task_id,
                "workflow_run_id": judge_input.workflow_run_id,
                "status": "running",
                "round_summary_count": len(judge_input.round_summary_ids),
                "agent_argument_count": len(judge_input.agent_argument_ids),
                "key_evidence_count": len(judge_input.key_evidence_ids),
                "enabled_tools": _enabled_judge_tools(judge_input.tool_access),
            },
        )
        if (
            not judge_input.round_summary_ids
            or not judge_input.agent_argument_ids
            or not judge_input.key_evidence_ids
        ):
            gaps = (
                EvidenceGap(
                    gap_type="missing_judge_inputs",
                    description="Judge 缺少 Round Summary、Agent Argument 或 key Evidence，不能形成完整判断。",
                ),
            )
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="failed",
                occurred_at=accepted_at,
                producer="judge_runtime",
                payload={
                    "runtime": "judge",
                    "task_id": task_id,
                    "workflow_run_id": judge_input.workflow_run_id,
                    "status": "insufficient_evidence",
                    "error_code": "insufficient_evidence",
                    "gap_types": _gap_types(gaps),
                    "gap_count": len(gaps),
                    "round_summary_count": len(judge_input.round_summary_ids),
                    "agent_argument_count": len(judge_input.agent_argument_ids),
                    "key_evidence_count": len(judge_input.key_evidence_ids),
                },
            )
            return JudgeRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=gaps,
            )

        summaries: list[RoundSummaryRecord] = []
        missing_summary_ids: list[str] = []
        for round_summary_id in judge_input.round_summary_ids:
            summary = self.repository.get_round_summary(round_summary_id)
            if summary is None:
                missing_summary_ids.append(round_summary_id)
                continue
            summaries.append(summary)
        if missing_summary_ids:
            gaps = (
                EvidenceGap(
                    gap_type="missing_round_summaries",
                    description=(
                        "Judge 请求的 Round Summary 尚未保存："
                        f"{', '.join(missing_summary_ids)}。"
                    ),
                ),
            )
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="failed",
                occurred_at=accepted_at,
                producer="judge_runtime",
                payload={
                    "runtime": "judge",
                    "task_id": task_id,
                    "workflow_run_id": judge_input.workflow_run_id,
                    "status": "insufficient_evidence",
                    "error_code": "insufficient_evidence",
                    "gap_types": _gap_types(gaps),
                    "gap_count": len(gaps),
                    "missing_round_summary_ids": list(missing_summary_ids),
                },
            )
            return JudgeRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=gaps,
            )

        arguments = [
            self.repository.get_argument(argument_id)
            for argument_id in judge_input.agent_argument_ids
        ]
        arguments = [argument for argument in arguments if argument is not None]
        if not arguments:
            gaps = (
                EvidenceGap(
                    gap_type="missing_agent_arguments",
                    description="Judge 请求的 Agent Argument 尚未保存。",
                ),
            )
            _append_runtime_event(
                self.runtime_event_repository,
                envelope=envelope,
                event_type="failed",
                occurred_at=accepted_at,
                producer="judge_runtime",
                payload={
                    "runtime": "judge",
                    "task_id": task_id,
                    "workflow_run_id": judge_input.workflow_run_id,
                    "status": "insufficient_evidence",
                    "error_code": "insufficient_evidence",
                    "gap_types": _gap_types(gaps),
                    "gap_count": len(gaps),
                    "requested_agent_argument_ids": list(judge_input.agent_argument_ids),
                },
            )
            return JudgeRunOutcome(
                task_id=task_id,
                status="insufficient_evidence",
                accepted_at=accepted_at,
                gaps=gaps,
            )

        details = []
        for evidence_id in judge_input.key_evidence_ids:
            try:
                details.append(self.evidence_store.get_evidence(envelope, evidence_id))
            except KeyError:
                gaps = (
                    EvidenceGap(
                        gap_type="missing_evidence_ids",
                        description=f"Judge 请求的 Evidence 不存在：{evidence_id}。",
                    ),
                )
                _append_runtime_event(
                    self.runtime_event_repository,
                    envelope=envelope,
                    event_type="failed",
                    occurred_at=accepted_at,
                    producer="judge_runtime",
                    payload={
                        "runtime": "judge",
                        "task_id": task_id,
                        "workflow_run_id": judge_input.workflow_run_id,
                        "status": "insufficient_evidence",
                        "error_code": "insufficient_evidence",
                        "gap_types": _gap_types(gaps),
                        "gap_count": len(gaps),
                        "missing_evidence_ids": [evidence_id],
                    },
                )
                return JudgeRunOutcome(
                    task_id=task_id,
                    status="insufficient_evidence",
                    accepted_at=accepted_at,
                    gaps=gaps,
                )

        judgment = _build_judgment_record(
            repository=self.repository,
            llm_provider=self.llm_provider,
            judge_input=judge_input,
            arguments=arguments,
            summaries=summaries,
            details=details,
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
                _append_runtime_event(
                    self.runtime_event_repository,
                    envelope=envelope,
                    event_type="tool_call_finished",
                    occurred_at=accepted_at,
                    producer="judge_runtime",
                    payload={
                        "runtime": "judge",
                        "task_id": task_id,
                        "workflow_run_id": judge_input.workflow_run_id,
                        "judgment_id": judgment.judgment_id,
                        "tool_call_id": call.tool_call_id,
                        "tool_name": call.tool_name,
                        "status": "completed",
                        "input": {"evidence_id": detail.evidence.evidence_id},
                        "result_ref": dict(call.result_ref),
                        "referenced_evidence_ids": list(call.referenced_evidence_ids),
                        "used_for": call.used_for,
                    },
                )

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
        _append_runtime_event(
            self.runtime_event_repository,
            envelope=envelope,
            event_type="completed",
            occurred_at=accepted_at,
            producer="judge_runtime",
            payload={
                "runtime": "judge",
                "task_id": task_id,
                "workflow_run_id": judge_input.workflow_run_id,
                "status": "completed",
                "judgment_id": judgment.judgment_id,
                "key_positive_evidence_ids": list(judgment.key_positive_evidence_ids),
                "key_negative_evidence_ids": list(judgment.key_negative_evidence_ids),
                "referenced_agent_argument_ids": list(judgment.referenced_agent_argument_ids),
                "saved_reference_count": len(saved_refs.accepted_references),
            },
        )
        return JudgeRunOutcome(
            task_id=task_id,
            status="completed",
            accepted_at=accepted_at,
            judgment_id=judgment.judgment_id,
        )


def _validate_workflow_scope(envelope: InternalCallEnvelope, workflow_run_id: str) -> None:
    if envelope.workflow_run_id != workflow_run_id:
        raise ValueError("workflow_run_id must match envelope.workflow_run_id")


def _summary_limitations(
    summaries: list[RoundSummaryRecord],
    argument_ids: tuple[str, ...],
) -> tuple[str, ...]:
    allowed_argument_ids = set(argument_ids)
    missing_argument_ids = _unique_ids(
        argument_id
        for summary in summaries
        for argument_id in summary.agent_argument_ids
        if argument_id not in allowed_argument_ids
    )
    if not missing_argument_ids:
        return ()
    return (
        "部分 Round Summary 引用了未纳入本次 Judge 输入的 Agent Argument："
        f"{', '.join(missing_argument_ids)}。",
    )


def _timestamp(envelope: InternalCallEnvelope) -> datetime:
    return envelope.analysis_time or datetime.now(UTC)


def _append_runtime_event(
    runtime_event_repository: Any | None,
    *,
    envelope: InternalCallEnvelope,
    event_type: str,
    occurred_at: datetime,
    producer: str,
    payload: dict[str, Any],
) -> None:
    if runtime_event_repository is None:
        return
    runtime_event_repository.append_event(
        RuntimeEvent(
            event_id="",
            event_type=event_type,
            occurred_at=occurred_at,
            correlation_id=envelope.correlation_id,
            workflow_run_id=envelope.workflow_run_id,
            producer=producer,
            payload=payload,
        )
    )


def _gap_types(gaps: tuple[EvidenceGap, ...]) -> list[str]:
    return [gap.gap_type for gap in gaps]


def _enabled_judge_tools(tool_access: JudgeToolAccess) -> list[str]:
    tools = []
    if tool_access.get_evidence_detail:
        tools.append("get_evidence_detail")
    if tool_access.get_raw_item:
        tools.append("get_raw_item")
    if tool_access.query_evidence_references:
        tools.append("query_evidence_references")
    return tools


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


def _llm_evidence_payload(details: list[Any]) -> list[dict[str, Any]]:
    payload = []
    for detail in details:
        evidence = detail.evidence
        structure = getattr(detail, "structure", None)
        payload.append(
            {
                "evidence_id": evidence.evidence_id,
                "ticker": evidence.ticker,
                "source": evidence.source,
                "source_type": evidence.source_type,
                "evidence_type": evidence.evidence_type,
                "title": evidence.title,
                "content": evidence.content,
                "url": evidence.url,
                "publish_time": evidence.publish_time.isoformat()
                if evidence.publish_time is not None
                else None,
                "source_quality": evidence.source_quality,
                "relevance": evidence.relevance,
                "freshness": evidence.freshness,
                "objective_summary": getattr(structure, "objective_summary", None),
                "claims": getattr(structure, "claims", None),
            }
        )
    return payload


def _filter_ids(values: list[str], allowed_ids: tuple[str, ...]) -> tuple[str, ...]:
    allowed = set(allowed_ids)
    return _unique_ids(value for value in values if value in allowed)


def _clean_key_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = _clean_key_value(value)
        return [cleaned] if cleaned is not None else []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            cleaned = _clean_key_value(item)
            if cleaned is not None and cleaned not in result:
                result.append(cleaned)
        return result
    cleaned = _clean_key_value(value)
    return [cleaned] if cleaned is not None else []


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(parsed, 1.0)), 2)


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


_AGENT_ARGUMENT_SYSTEM_PROMPT = """You are an investment research debate agent.
Return exactly one JSON object and no markdown.
Use only the provided Evidence IDs. Do not invent Evidence, facts, URLs, SearchTasks, or provider calls.
You may make analytical arguments, but every important claim must cite provided Evidence IDs.
Never include buy/sell/hold recommendations or trade instructions in Evidence-facing fields."""


_ROUND_SUMMARY_SYSTEM_PROMPT = """You summarize one debate round for audit navigation.
Return exactly one JSON object and no markdown.
Do not introduce new facts. Compress only the provided Agent Arguments and preserve traceability."""


_JUDGE_SYSTEM_PROMPT = """You are the Judge Runtime for an evidence-driven investment workflow.
Return exactly one JSON object and no markdown.
Use only the provided Agent Arguments and Evidence IDs.
Do not call search, do not invent Evidence, and do not include ungrounded facts.
The judgment may state a bounded final_signal, confidence, risks, limitations, and next checks."""
