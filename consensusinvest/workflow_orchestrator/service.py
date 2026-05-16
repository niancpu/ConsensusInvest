"""Workflow Orchestrator service."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import os
from threading import Lock
from typing import Any
from uuid import uuid4

from consensusinvest.agent_swarm import AgentSwarmRuntime, JudgeRuntime
from consensusinvest.agent_swarm.models import EvidenceGap, EvidenceSelection, JudgeToolAccess, SuggestedSearch
from consensusinvest.agent_swarm.presentation import (
    display_agent_argument_text,
    display_judgment_reasoning,
    display_round_summary_text,
)
from consensusinvest.entities import EntityRecord
from consensusinvest.evidence_store import EvidenceQuery, EvidenceStoreClient
from consensusinvest.evidence_store.presentation import display_text_for_raw_payload
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
        entity_repository: Any | None = None,
    ) -> None:
        self.repository = repository or InMemoryWorkflowRepository()
        self.evidence_store = evidence_store
        self.agent_swarm = agent_swarm
        self.judge = judge
        self.entity_repository = entity_repository
        self.acquisition = acquisition or EvidenceAcquisitionService()
        self.evidence_structurer = evidence_structurer or EvidenceStructuringAgent(
            evidence_store=evidence_store
        )
        self._run_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="workflow-run")
        self._run_futures: dict[str, Future] = {}
        self._run_futures_lock = Lock()

    def create_run(self, request: WorkflowRunCreate) -> WorkflowRunRecord:
        now = _timestamp(request.analysis_time)
        ticker = _normalize_ticker(request.ticker)
        stock_code = _normalize_stock_code(request.stock_code, ticker=ticker)
        entity_id = request.entity_id or f"ent_company_{ticker}"
        workflow_run_id = self.repository.new_workflow_run_id(
            ticker=ticker,
            analysis_time=request.analysis_time,
        )
        run = WorkflowRunRecord(
            workflow_run_id=workflow_run_id,
            correlation_id=f"corr_{uuid4().hex[:12]}",
            ticker=ticker,
            analysis_time=request.analysis_time,
            workflow_config_id=request.workflow_config_id,
            status="queued",
            stage="queued",
            query=request.query,
            options=request.options,
            entity_id=entity_id,
            stock_code=stock_code,
            created_at=now,
        )
        self._upsert_workflow_entity(run)
        self.repository.create_run(run)
        self.repository.append_event(
            workflow_run_id,
            "workflow_queued",
            {"ticker": ticker, "workflow_config_id": request.workflow_config_id},
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
            self.start_run(workflow_run_id)
        return run

    def start_run(self, workflow_run_id: str) -> None:
        self._required_run(workflow_run_id)
        with self._run_futures_lock:
            future = self._run_futures.get(workflow_run_id)
            if future is not None and not future.done():
                return
            self._run_futures[workflow_run_id] = self._run_executor.submit(
                self.run_once,
                workflow_run_id,
            )

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
        run = self.repository.update_run(workflow_run_id, progress=progress)

        envelope = self._envelope(run, suffix="agent_swarm")
        run = self.repository.update_run(workflow_run_id, stage="debate")
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
        run = self.repository.update_run(workflow_run_id, progress=progress, stage="judge")
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
        nodes: list[WorkflowTraceNode] = []
        edges: list[WorkflowTraceEdge] = []
        judgment = self.agent_swarm.repository.get_judgment_by_workflow(workflow_run_id)
        if judgment is not None:
            nodes.append(
                WorkflowTraceNode(
                    node_type="judgment",
                    node_id=judgment.judgment_id,
                    title="最终判断",
                    summary=display_judgment_reasoning(
                        reasoning=judgment.reasoning,
                        final_signal=judgment.final_signal,
                        confidence=judgment.confidence,
                        positive_evidence_ids=judgment.key_positive_evidence_ids,
                        negative_evidence_ids=judgment.key_negative_evidence_ids,
                        referenced_agent_argument_ids=judgment.referenced_agent_argument_ids,
                    ),
                )
            )
        for argument in self.agent_swarm.repository.list_arguments(workflow_run_id):
            nodes.append(
                WorkflowTraceNode(
                    node_type="agent_argument",
                    node_id=argument.agent_argument_id,
                    title=f"{argument.agent_id} 第 {argument.round} 轮",
                    summary=display_agent_argument_text(
                        argument=argument.argument,
                        agent_id=argument.agent_id,
                        role=argument.role,
                        round_number=argument.round,
                        confidence=argument.confidence,
                        referenced_evidence_ids=argument.referenced_evidence_ids,
                        counter_evidence_ids=argument.counter_evidence_ids,
                    ),
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
                    title=f"第 {summary.round} 轮摘要",
                    summary=display_round_summary_text(
                        summary=summary.summary,
                        round_number=summary.round,
                        agent_argument_ids=summary.agent_argument_ids,
                        referenced_evidence_ids=summary.referenced_evidence_ids,
                        disputed_evidence_ids=summary.disputed_evidence_ids,
                    ),
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
        evidence_items = self._query_evidence(run, limit=100)
        raw_items_by_ref = self._raw_items_by_ref(run, evidence_items)
        for evidence in evidence_items:
            raw_item = raw_items_by_ref.get(evidence.raw_ref)
            structure_summary = self._evidence_structure_summary(run, evidence.evidence_id)
            trace_summary = display_text_for_raw_payload(
                structure_summary or evidence.content,
                raw_item.raw_payload if raw_item is not None else None,
                source_label=_source_label(raw_item, evidence.source),
            )
            nodes.append(
                WorkflowTraceNode(
                    node_type="evidence",
                    node_id=evidence.evidence_id,
                    title=evidence.title or evidence.evidence_id,
                    summary=trace_summary or evidence.evidence_type or evidence.source or "",
                )
            )
            nodes.append(
                WorkflowTraceNode(
                    node_type="raw_item",
                    node_id=evidence.raw_ref,
                    title=(raw_item.title if raw_item is not None else None) or f"Raw item {evidence.raw_ref}",
                    summary=_raw_item_source_summary(raw_item) if raw_item is not None else evidence.source or "",
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

    def _upsert_workflow_entity(self, run: WorkflowRunRecord) -> None:
        if self.entity_repository is None or run.entity_id is None:
            return
        upsert = getattr(self.entity_repository, "upsert_entity", None)
        if not callable(upsert):
            return

        existing = None
        getter = getattr(self.entity_repository, "get_entity", None)
        if callable(getter):
            existing = getter(run.entity_id)

        aliases = _merge_aliases(
            getattr(existing, "aliases", ()),
            (run.ticker, run.stock_code),
        )
        record = EntityRecord(
            entity_id=run.entity_id,
            entity_type=getattr(existing, "entity_type", "company") if existing is not None else "company",
            name=getattr(existing, "name", None) or run.stock_code or run.ticker,
            aliases=aliases,
            description=getattr(existing, "description", None)
            or "A-share company entity inferred from workflow input.",
        )
        upsert(record)

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

    def _evidence_structure_summary(self, run: WorkflowRunRecord, evidence_id: str) -> str | None:
        envelope = self._envelope(run, suffix="trace_evidence_detail", require_idempotency=False)
        try:
            detail = self.evidence_store.get_evidence(envelope, evidence_id)
        except KeyError:
            return None
        if detail.structure is not None and detail.structure.objective_summary:
            return detail.structure.objective_summary
        return None

    def _raw_items_by_ref(self, run: WorkflowRunRecord, evidence_items: list[Any]) -> dict[str, Any]:
        envelope = self._envelope(run, suffix="trace_raw_items", require_idempotency=False)
        rows: dict[str, Any] = {}
        for evidence in evidence_items:
            try:
                rows[evidence.raw_ref] = self.evidence_store.get_raw(envelope, evidence.raw_ref)
            except KeyError:
                continue
        return rows

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
            {
                "code": "insufficient_evidence",
                "failed_stage": run.stage,
                "gaps": [_to_plain(gap) for gap in gaps],
            },
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
            {"code": code, "failed_stage": run.stage, "message": message},
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


def _normalize_ticker(value: str) -> str:
    text = value.strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _normalize_stock_code(value: str | None, *, ticker: str) -> str | None:
    text = (value or "").strip().upper()
    if text:
        if "." in text:
            prefix, suffix = text.split(".", 1)
            return f"{prefix}.{suffix}" if prefix and suffix else text
        if text.isdigit() and len(text) == 6:
            return f"{text}.{_a_share_suffix(text)}"
        return text
    if ticker.isdigit() and len(ticker) == 6:
        return f"{ticker}.{_a_share_suffix(ticker)}"
    return None


def _a_share_suffix(ticker: str) -> str:
    return "SH" if ticker.startswith(("5", "6", "9")) else "SZ"


def _merge_aliases(*groups: Any) -> tuple[str, ...]:
    aliases: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if group is None:
            continue
        values = group if isinstance(group, (list, tuple, set)) else (group,)
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(text)
    return tuple(aliases)


def _raw_item_source_summary(raw_item: Any) -> str:
    parts = [
        str(value)
        for value in (
            getattr(raw_item, "source", None),
            getattr(raw_item, "source_type", None),
            getattr(raw_item, "url", None),
        )
        if value
    ]
    return " · ".join(parts)


def _source_label(raw_item: Any | None, fallback: str | None) -> str | None:
    source = (getattr(raw_item, "source", None) if raw_item is not None else fallback) or ""
    normalized = str(source).strip().lower()
    if normalized == "akshare":
        return "AkShare"
    if normalized == "tushare":
        return "TuShare"
    return str(source) if source else fallback


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
