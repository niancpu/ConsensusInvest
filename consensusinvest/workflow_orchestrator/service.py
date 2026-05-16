"""Workflow Orchestrator service."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import os
from typing import Any
from uuid import uuid4

from consensusinvest.agent_swarm import AgentSwarmRuntime, JudgeRuntime
from consensusinvest.agent_swarm.models import EvidenceGap, EvidenceSelection, JudgeToolAccess, SuggestedSearch
from consensusinvest.evidence_store import EvidenceQuery, EvidenceStoreClient
from consensusinvest.evidence_structuring import EvidenceStructuringAgent
from consensusinvest.runtime import InternalCallEnvelope

from .acquisition import EvidenceAcquisitionService, build_gap_fill_request
from .models import (
    WorkflowEventRecord,
    WorkflowProgress,
    WorkflowRunCreate,
    WorkflowRunRecord,
    WorkflowTraceEdge,
    WorkflowTraceNode,
)
from .repository import InMemoryWorkflowRepository


class WorkflowOrchestrator:
    def __init__(
        self,
        *,
        repository: InMemoryWorkflowRepository | None = None,
        evidence_store: EvidenceStoreClient,
        agent_swarm: AgentSwarmRuntime,
        judge: JudgeRuntime,
        acquisition: EvidenceAcquisitionService | None = None,
        evidence_structurer: EvidenceStructuringAgent | None = None,
    ) -> None:
        self.repository = repository or InMemoryWorkflowRepository()
        self.evidence_store = evidence_store
        self.agent_swarm = agent_swarm
        self.judge = judge
        self.acquisition = acquisition or EvidenceAcquisitionService()
        self.evidence_structurer = evidence_structurer or EvidenceStructuringAgent(
            evidence_store=evidence_store
        )

    def create_run(self, request: WorkflowRunCreate) -> WorkflowRunRecord:
        now = _timestamp(request.analysis_time)
        workflow_run_id = self.repository.new_workflow_run_id(
            ticker=request.ticker,
            analysis_time=request.analysis_time,
        )
        run = WorkflowRunRecord(
            workflow_run_id=workflow_run_id,
            correlation_id=f"corr_{uuid4().hex[:12]}",
            ticker=request.ticker,
            analysis_time=request.analysis_time,
            workflow_config_id=request.workflow_config_id,
            status="queued",
            stage="queued",
            query=request.query,
            options=request.options,
            entity_id=request.entity_id or f"ent_company_{request.ticker}",
            stock_code=request.stock_code,
            created_at=now,
        )
        self.repository.create_run(run)
        self.repository.append_event(
            workflow_run_id,
            "workflow_queued",
            {"ticker": request.ticker, "workflow_config_id": request.workflow_config_id},
            created_at=now,
        )
        if request.options.auto_run:
            config_error = self._start_configuration_error(run)
            if config_error is not None:
                return self._mark_failed(
                    run,
                    "missing_runtime_configuration",
                    config_error,
                )
            return self.run_once(workflow_run_id)
        return run

    def run_once(self, workflow_run_id: str) -> WorkflowRunRecord:
        run = self._required_run(workflow_run_id)
        started_at = run.started_at or _timestamp(run.analysis_time)
        run = self.repository.update_run(
            workflow_run_id,
            status="running",
            stage="normalizing_evidence",
            started_at=started_at,
        )
        self.repository.append_event(workflow_run_id, "workflow_started", {}, created_at=started_at)
        config_error = self._start_configuration_error(run)
        if config_error is not None:
            return self._mark_failed(
                run,
                "missing_runtime_configuration",
                config_error,
            )
        run = self.repository.update_run(workflow_run_id, stage="evidence_selection")
        evidence_ids = self._select_evidence(run)
        if not evidence_ids:
            run, evidence_ids = self._collect_initial_evidence(run)
            if not evidence_ids and run.search_task_ids:
                return self._mark_failed(
                    run,
                    "evidence_acquisition_failed",
                    "No Evidence was ingested after the initial workflow acquisition task.",
                )
        run = self.repository.update_run(workflow_run_id, stage="structuring_evidence")
        self._structure_selected_evidence(run, evidence_ids)
        progress = WorkflowProgress(
            raw_items_collected=len(evidence_ids),
            evidence_items_normalized=len(evidence_ids),
            evidence_items_structured=self._structured_count(run, evidence_ids),
            agent_arguments_completed=0,
        )
        self.repository.update_run(workflow_run_id, progress=progress)

        envelope = self._envelope(run, suffix="agent_swarm")
        self.repository.update_run(workflow_run_id, stage="debate")
        try:
            swarm_outcome = self.agent_swarm.run(
                envelope,
                {
                    "workflow_run_id": workflow_run_id,
                    "ticker": run.ticker,
                    "entity_id": run.entity_id,
                    "workflow_config_id": run.workflow_config_id,
                    "evidence_selection": EvidenceSelection(evidence_ids=tuple(evidence_ids)),
                    "history": {"previous_judgment_ids": []},
                },
            )
        except Exception as exc:
            return self._mark_failed(
                run,
                "agent_swarm_failed",
                _runtime_error_message(exc, stage="Agent Swarm"),
            )
        if swarm_outcome.status == "insufficient_evidence":
            return self._mark_insufficient(run, tuple(swarm_outcome.gaps))
        for argument_id in swarm_outcome.agent_argument_ids:
            argument = self.agent_swarm.repository.get_argument(argument_id)
            self.repository.append_event(
                workflow_run_id,
                "agent_argument_completed",
                {
                    "agent_argument_id": argument_id,
                    "round": argument.round if argument is not None else None,
                },
                created_at=swarm_outcome.accepted_at,
            )
        round_summary_ids = _round_summary_ids(swarm_outcome)
        for round_summary_id in round_summary_ids:
            summary = self.agent_swarm.repository.get_round_summary(round_summary_id)
            self.repository.append_event(
                workflow_run_id,
                "round_summary_completed",
                {
                    "round_summary_id": round_summary_id,
                    "round": summary.round if summary is not None else None,
                },
                created_at=swarm_outcome.accepted_at,
            )
        progress = WorkflowProgress(
            raw_items_collected=len(evidence_ids),
            evidence_items_normalized=len(evidence_ids),
            evidence_items_structured=self._structured_count(run, evidence_ids),
            agent_arguments_completed=len(swarm_outcome.agent_argument_ids),
        )
        self.repository.update_run(workflow_run_id, progress=progress, stage="judge")
        self.repository.append_event(workflow_run_id, "judge_started", {}, created_at=_timestamp(run.analysis_time))

        try:
            judge_outcome = self.judge.run(
                self._envelope(run, suffix="judge"),
                {
                    "workflow_run_id": workflow_run_id,
                    "round_summary_ids": list(round_summary_ids),
                    "agent_argument_ids": list(swarm_outcome.agent_argument_ids),
                    "key_evidence_ids": evidence_ids,
                    "tool_access": JudgeToolAccess(),
                },
            )
        except Exception as exc:
            return self._mark_failed(
                run,
                "judge_failed",
                _runtime_error_message(exc, stage="Judge"),
            )
        if judge_outcome.status == "insufficient_evidence":
            return self._mark_insufficient(run, tuple(judge_outcome.gaps))
        judgment = self.agent_swarm.repository.get_judgment(judge_outcome.judgment_id or "")
        if judgment is None:
            return self._mark_failed(run, "missing_judgment", "Judge completed without saved judgment.")

        completed_at = judgment.created_at or _timestamp(run.analysis_time)
        for tool_call in self.agent_swarm.repository.list_tool_calls(judgment.judgment_id):
            self.repository.append_event(
                workflow_run_id,
                "judge_tool_call_completed",
                _judge_tool_call_payload(tool_call),
                created_at=tool_call.created_at or completed_at,
            )
        self.repository.append_event(
            workflow_run_id,
            "judgment_completed",
            {"judgment_id": judgment.judgment_id},
            created_at=completed_at,
        )
        self.repository.append_event(
            workflow_run_id,
            "workflow_completed",
            {"judgment_id": judgment.judgment_id},
            created_at=completed_at,
        )
        return self.repository.update_run(
            workflow_run_id,
            status="completed",
            stage="completed",
            completed_at=completed_at,
            judgment_id=judgment.judgment_id,
            final_signal=judgment.final_signal,
            confidence=judgment.confidence,
            progress=progress,
        )

    def list_runs(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WorkflowRunRecord], int]:
        return self.repository.list_runs(ticker=ticker, status=status, limit=limit, offset=offset)

    def get_run(self, workflow_run_id: str) -> WorkflowRunRecord | None:
        return self.repository.get_run(workflow_run_id)

    def snapshot(
        self,
        workflow_run_id: str,
        *,
        include_events: bool = False,
        max_evidence: int = 100,
        max_arguments: int = 100,
    ) -> dict[str, Any]:
        run = self._required_run(workflow_run_id)
        evidence = self._query_evidence(run, limit=max_evidence)
        judgment = self.agent_swarm.repository.get_judgment_by_workflow(workflow_run_id)
        judge_tool_calls = (
            self.agent_swarm.repository.list_tool_calls(judgment.judgment_id)
            if judgment is not None
            else []
        )
        data: dict[str, Any] = {
            "workflow_run": run,
            "evidence_items": evidence,
            "agent_runs": self.agent_swarm.repository.list_agent_runs(workflow_run_id),
            "agent_arguments": self.agent_swarm.repository.list_arguments(workflow_run_id)[:max_arguments],
            "round_summaries": self.agent_swarm.repository.list_round_summaries(workflow_run_id),
            "judgment": judgment,
            "judge_tool_calls": judge_tool_calls,
            "last_event_sequence": self.repository.last_event_sequence(workflow_run_id),
        }
        if include_events:
            data["events"] = self.repository.list_events(workflow_run_id)
        return data

    def trace(self, workflow_run_id: str) -> tuple[list[WorkflowTraceNode], list[WorkflowTraceEdge]]:
        run = self._required_run(workflow_run_id)
        if run.status != "completed":
            return [], []
        nodes: list[WorkflowTraceNode] = []
        edges: list[WorkflowTraceEdge] = []
        judgment = self.agent_swarm.repository.get_judgment_by_workflow(workflow_run_id)
        if judgment is not None:
            nodes.append(
                WorkflowTraceNode(
                    node_type="judgment",
                    node_id=judgment.judgment_id,
                    title="Final judgment",
                    summary=judgment.reasoning,
                )
            )
        for argument in self.agent_swarm.repository.list_arguments(workflow_run_id):
            nodes.append(
                WorkflowTraceNode(
                    node_type="agent_argument",
                    node_id=argument.agent_argument_id,
                    title=f"{argument.agent_id} round {argument.round}",
                    summary=argument.argument,
                )
            )
            if judgment is not None and argument.agent_argument_id in judgment.referenced_agent_argument_ids:
                edges.append(
                    WorkflowTraceEdge(
                        from_node_id=judgment.judgment_id,
                        to_node_id=argument.agent_argument_id,
                        edge_type="uses_argument",
                    )
                )
            for evidence_id in [*argument.referenced_evidence_ids, *argument.counter_evidence_ids]:
                edges.append(
                    WorkflowTraceEdge(
                        from_node_id=argument.agent_argument_id,
                        to_node_id=evidence_id,
                        edge_type="supports" if evidence_id in argument.referenced_evidence_ids else "counters",
                    )
                )
        for summary in self.agent_swarm.repository.list_round_summaries(workflow_run_id):
            nodes.append(
                WorkflowTraceNode(
                    node_type="round_summary",
                    node_id=summary.round_summary_id,
                    title=f"Round {summary.round} summary",
                    summary=summary.summary,
                )
            )
            for argument_id in summary.agent_argument_ids:
                edges.append(
                    WorkflowTraceEdge(
                        from_node_id=summary.round_summary_id,
                        to_node_id=argument_id,
                        edge_type="summarizes_argument",
                    )
                )
            if judgment is not None:
                edges.append(
                    WorkflowTraceEdge(
                        from_node_id=judgment.judgment_id,
                        to_node_id=summary.round_summary_id,
                        edge_type="uses_round_summary",
                    )
                )
        for evidence in self._query_evidence(run, limit=100):
            nodes.append(
                WorkflowTraceNode(
                    node_type="evidence",
                    node_id=evidence.evidence_id,
                    title=evidence.title or evidence.evidence_id,
                    summary=evidence.content or evidence.evidence_type or "",
                )
            )
            nodes.append(
                WorkflowTraceNode(
                    node_type="raw_item",
                    node_id=evidence.raw_ref,
                    title=f"Raw item {evidence.raw_ref}",
                    summary=evidence.source or "",
                )
            )
            edges.append(
                WorkflowTraceEdge(
                    from_node_id=evidence.evidence_id,
                    to_node_id=evidence.raw_ref,
                    edge_type="derived_from",
                )
            )
        return nodes, edges

    def list_events(
        self,
        workflow_run_id: str,
        *,
        after_sequence: int | None = None,
    ) -> list[WorkflowEventRecord]:
        self._required_run(workflow_run_id)
        return self.repository.list_events(workflow_run_id, after_sequence=after_sequence)

    def _select_evidence(self, run: WorkflowRunRecord) -> list[str]:
        return [item.evidence_id for item in self._query_evidence(run, limit=run.query.max_results)]

    def _collect_initial_evidence(self, run: WorkflowRunRecord) -> tuple[WorkflowRunRecord, list[str]]:
        search_pool = getattr(self.acquisition, "search_pool", None)
        if search_pool is None:
            return run, []

        self.repository.update_run(run.workflow_run_id, stage="collecting_raw_items")
        self.repository.append_event(
            run.workflow_run_id,
            "connector_started",
            {"sources": list(run.query.sources), "reason": "initial_evidence_acquisition"},
            created_at=_timestamp(run.analysis_time),
        )
        gap = EvidenceGap(
            gap_type="missing_initial_evidence",
            description="No ingested Evidence matched the workflow query before Agent Swarm.",
            suggested_search=SuggestedSearch(
                target_entity_ids=(run.entity_id,) if run.entity_id else (),
                evidence_types=run.query.evidence_types,
                lookback_days=run.query.lookback_days,
                keywords=(run.stock_code or run.ticker, run.ticker),
            ),
        )
        try:
            receipt = self.acquisition.request_gap_fill(
                self._envelope(run, suffix="initial_evidence"),
                build_gap_fill_request(
                    workflow_run_id=run.workflow_run_id,
                    gap=gap,
                    ticker=run.ticker,
                    stock_code=run.stock_code,
                    entity_id=run.entity_id,
                    query=run.query,
                ),
            )
        except RuntimeError as exc:
            self.repository.append_event(
                run.workflow_run_id,
                "connector_progress",
                {
                    "status": "failed",
                    "reason": "initial_evidence_acquisition_unavailable",
                    "message": str(exc),
                },
                created_at=_timestamp(run.analysis_time),
            )
            return run, []

        task_id = _value(receipt, "task_id")
        if task_id is None:
            return run, []

        run_task_once = getattr(search_pool, "run_task_once", None)
        if callable(run_task_once):
            run_task_once(str(task_id))
        self.repository.append_event(
            run.workflow_run_id,
            "connector_progress",
            {"status": "completed", "task_id": str(task_id), "reason": "initial_evidence_acquisition"},
            created_at=_timestamp(run.analysis_time),
        )
        updated_run = self.repository.update_run(
            run.workflow_run_id,
            search_task_ids=(*run.search_task_ids, str(task_id)),
        )
        return updated_run, self._select_evidence(updated_run)

    def _structure_selected_evidence(self, run: WorkflowRunRecord, evidence_ids: list[str]) -> None:
        for evidence_id in evidence_ids:
            self.repository.append_event(
                run.workflow_run_id,
                "evidence_structuring_started",
                {"evidence_id": evidence_id, "agent_id": self.evidence_structurer.agent_id},
                created_at=_timestamp(run.analysis_time),
            )
            outcome = self.evidence_structurer.structure_evidence(
                self._envelope(run, suffix=f"structure_{evidence_id}"),
                evidence_id,
            )
            if outcome.status != "structured" or outcome.structure is None:
                continue
            self.repository.append_event(
                run.workflow_run_id,
                "evidence_structured",
                {
                    "evidence_id": evidence_id,
                    "evidence_structure_id": outcome.structure.structure_id,
                    "created_by_agent_id": outcome.structure.created_by_agent_id,
                },
                created_at=outcome.structure.created_at or _timestamp(run.analysis_time),
            )

    def _query_evidence(self, run: WorkflowRunRecord, *, limit: int) -> list[Any]:
        page = self.evidence_store.query_evidence(
            self._envelope(run, suffix="query_evidence", require_idempotency=False),
            EvidenceQuery(
                ticker=run.ticker,
                entity_ids=(run.entity_id,) if run.entity_id else (),
                workflow_run_id=run.workflow_run_id,
                evidence_types=run.query.evidence_types,
                sources=run.query.sources,
                publish_time_lte=run.analysis_time,
                limit=limit,
            ),
        )
        return list(page.items)

    def _structured_count(self, run: WorkflowRunRecord, evidence_ids: list[str]) -> int:
        count = 0
        envelope = self._envelope(run, suffix="structure_count", require_idempotency=False)
        for evidence_id in evidence_ids:
            try:
                if self.evidence_store.get_evidence(envelope, evidence_id).structure is not None:
                    count += 1
            except KeyError:
                continue
        return count

    def _search_configuration_error(self, run: WorkflowRunRecord) -> str | None:
        search_pool = getattr(self.acquisition, "search_pool", None)
        unavailable_sources: tuple[str, ...] = ()
        if search_pool is not None:
            checker = getattr(search_pool, "unavailable_sources", None)
            if callable(checker):
                unavailable_sources = tuple(checker(run.query.sources))
            else:
                providers = getattr(search_pool, "providers", {})
                fallback_provider = getattr(search_pool, "provider", None)
                if fallback_provider is None:
                    unavailable_sources = tuple(
                        source for source in run.query.sources if source not in providers
                    )
        if unavailable_sources:
            source_details = "，".join(
                f"{source}（{_source_configuration_hint(source)}）"
                for source in unavailable_sources
            )
            return (
                "分析无法开始：当前 workflow 请求的数据源未配置或不可用："
                f"{source_details}。"
                "请在后端 .env 中配置对应数据源密钥，或从本次请求的 query.sources 中移除这些数据源。"
            )
        return None

    def _start_configuration_error(self, run: WorkflowRunRecord) -> str | None:
        errors = [
            message
            for message in (
                self._search_configuration_error(run),
                self._llm_configuration_error(),
            )
            if message is not None
        ]
        if not errors:
            return None
        return "\n".join(errors)

    def _llm_configuration_error(self) -> str | None:
        missing_llm_groups = _missing_llm_credential_groups(self.agent_swarm, self.judge)
        if missing_llm_groups:
            required = "；".join(" 或 ".join(group) for group in missing_llm_groups)
            return (
                "分析无法开始：Agent/Judge 模型已启用，但没有可用的模型 API key。"
                f"请在后端 .env 中配置：{required}，然后重新运行 workflow。"
            )
        return None

    def _mark_insufficient(self, run: WorkflowRunRecord, gaps: tuple) -> WorkflowRunRecord:
        search_task_ids: list[str] = []
        for gap in gaps:
            self.repository.append_event(
                run.workflow_run_id,
                "connector_progress",
                {"gap_type": gap.gap_type, "description": gap.description},
                created_at=_timestamp(run.analysis_time),
            )
            if gap.suggested_search is None:
                continue
            try:
                receipt = self.acquisition.request_gap_fill(
                    self._envelope(run, suffix=f"gap_{gap.gap_type}"),
                    build_gap_fill_request(
                        workflow_run_id=run.workflow_run_id,
                        gap=gap,
                        ticker=run.ticker,
                        stock_code=run.stock_code,
                        entity_id=run.entity_id,
                        query=run.query,
                    ),
                )
                task_id = getattr(receipt, "task_id", None)
                if task_id is not None:
                    search_task_ids.append(str(task_id))
            except RuntimeError:
                pass
        self.repository.append_event(
            run.workflow_run_id,
            "workflow_failed",
            {"code": "insufficient_evidence", "gaps": [_to_plain(gap) for gap in gaps]},
            created_at=_timestamp(run.analysis_time),
        )
        return self.repository.update_run(
            run.workflow_run_id,
            status="failed",
            stage="failed",
            completed_at=_timestamp(run.analysis_time),
            evidence_gaps=gaps,
            search_task_ids=tuple(search_task_ids),
            failure_code="insufficient_evidence",
            failure_message="Evidence is insufficient for a complete workflow judgment.",
        )

    def _mark_failed(self, run: WorkflowRunRecord, code: str, message: str) -> WorkflowRunRecord:
        self.repository.append_event(
            run.workflow_run_id,
            "workflow_failed",
            {"code": code, "message": message},
            created_at=_timestamp(run.analysis_time),
        )
        return self.repository.update_run(
            run.workflow_run_id,
            status="failed",
            stage="failed",
            completed_at=_timestamp(run.analysis_time),
            failure_code=code,
            failure_message=message,
        )

    def _required_run(self, workflow_run_id: str) -> WorkflowRunRecord:
        run = self.repository.get_run(workflow_run_id)
        if run is None:
            raise KeyError(f"workflow_run_not_found: {workflow_run_id}")
        return run

    def _envelope(
        self,
        run: WorkflowRunRecord,
        *,
        suffix: str,
        require_idempotency: bool = True,
    ) -> InternalCallEnvelope:
        return InternalCallEnvelope(
            request_id=f"req_{run.workflow_run_id}_{suffix}",
            correlation_id=run.correlation_id,
            workflow_run_id=run.workflow_run_id,
            analysis_time=run.analysis_time,
            requested_by="workflow_orchestrator",
            idempotency_key=f"{run.workflow_run_id}_{suffix}" if require_idempotency else None,
            trace_level="standard",
        )


def _timestamp(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _round_summary_ids(swarm_outcome: Any) -> tuple[str, ...]:
    ids = tuple(getattr(swarm_outcome, "round_summary_ids", ()) or ())
    if ids:
        return ids
    round_summary_id = getattr(swarm_outcome, "round_summary_id", None)
    return (round_summary_id,) if round_summary_id else ()


def _to_plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_plain(asdict(value))
    if isinstance(value, dict):
        return {key: _to_plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(child) for child in value]
    return value


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _judge_tool_call_payload(tool_call: Any) -> dict[str, Any]:
    return {
        "tool_call_id": tool_call.tool_call_id,
        "judgment_id": tool_call.judgment_id,
        "tool_name": tool_call.tool_name,
        "input": _to_plain(dict(tool_call.input)),
        "output_summary": tool_call.output_summary,
        "referenced_evidence_ids": list(tool_call.referenced_evidence_ids),
    }


def _runtime_error_message(exc: Exception, *, stage: str) -> str:
    text = str(exc)
    if _is_missing_llm_credentials(text):
        provider = os.environ.get("CONSENSUSINVEST_LLM_PROVIDER", "").strip() or "litellm"
        return (
            f"{stage} 调用模型失败：当前后端使用 {provider}，但没有可用的模型 API key。"
            "请在后端环境变量中配置对应模型密钥后重新运行 workflow。"
        )
    if "llm_invalid_json" in text:
        return f"{stage} 调用模型失败：模型返回内容不是有效 JSON，请检查模型配置或提示词约束。"
    if "llm_empty_response" in text:
        return f"{stage} 调用模型失败：模型没有返回内容，请稍后重试或检查模型服务。"
    return f"{stage} 执行失败：{text or exc.__class__.__name__}"


def _source_configuration_hint(source: str) -> str:
    normalized = source.strip().lower()
    if normalized == "tavily":
        return "缺少 TAVILY_API_KEY"
    if normalized == "exa":
        return "缺少 EXA_API_KEY"
    if normalized == "tushare":
        return "缺少 CONSENSUSINVEST_TUSHARE_TOKEN 或 TUSHARE_TOKEN"
    if normalized == "akshare":
        return "AkShare provider 未启用或 akshare 包不可用"
    return "provider 未注册"


def _missing_llm_credential_groups(*runtimes: Any) -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    for runtime in runtimes:
        provider = getattr(runtime, "llm_provider", None)
        if provider is None:
            continue
        checker = getattr(provider, "missing_credential_env_groups", None)
        if not callable(checker):
            continue
        groups.extend(tuple(group) for group in checker())
    result: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for group in groups:
        if group in seen:
            continue
        seen.add(group)
        result.append(group)
    return tuple(result)


def _is_missing_llm_credentials(text: str) -> bool:
    normalized = text.lower()
    return (
        "missing credentials" in normalized
        or "api_key" in normalized
        and (
            "openai_api_key" in normalized
            or "api key" in normalized
            or "api_key" in normalized
        )
    )


__all__ = ["WorkflowOrchestrator"]
