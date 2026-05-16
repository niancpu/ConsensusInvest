"""Workflow API routes."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from consensusinvest.common.errors import NotFoundError
from consensusinvest.common.response import ListPagination, ListResponse, SingleResponse
from consensusinvest.agent_swarm.presentation import (
    display_agent_argument_text,
    display_agent_limitations,
    display_chinese_notes,
    display_judgment_reasoning,
    display_round_summary_text,
    sanitize_role_output_for_display,
)
from consensusinvest.runtime.wiring import AppRuntime

from .models import WorkflowOptions, WorkflowQuery, WorkflowRunCreate, WorkflowRunRecord
from .schemas import (
    AgentArgumentSnapshotView,
    AgentRunSnapshotView,
    EvidenceItemSnapshotView,
    JudgeToolCallSnapshotView,
    JudgmentSnapshotView,
    RoundSummarySnapshotView,
    TraceEdgeView,
    TraceNodeView,
    WorkflowEventView,
    WorkflowLinksView,
    WorkflowProgressView,
    WorkflowRunCreateRequest,
    WorkflowRunCreateView,
    WorkflowRunDetailView,
    WorkflowRunListItemView,
    WorkflowSnapshotRunView,
    WorkflowSnapshotView,
    WorkflowTraceView,
)
from .service import WorkflowOrchestrator

router = APIRouter(prefix="/api/v1", tags=["workflow"])


def get_workflow_service(request: Request) -> WorkflowOrchestrator:
    runtime: AppRuntime = request.app.state.runtime
    return runtime.workflow_service


@router.post("/workflow-runs", status_code=202, response_model=SingleResponse[WorkflowRunCreateView])
def create_workflow_run(
    request: WorkflowRunCreateRequest,
    service: WorkflowOrchestrator = Depends(get_workflow_service),
) -> SingleResponse[WorkflowRunCreateView]:
    run = service.create_run(
        WorkflowRunCreate(
            ticker=request.ticker,
            analysis_time=request.analysis_time,
            workflow_config_id=request.workflow_config_id,
            query=WorkflowQuery(
                lookback_days=request.query.lookback_days,
                sources=tuple(request.query.sources),
                evidence_types=tuple(request.query.evidence_types),
                max_results=request.query.max_results,
            ),
            options=WorkflowOptions(
                stream=request.options.stream,
                include_raw_payload=request.options.include_raw_payload,
                auto_run=request.options.auto_run,
            ),
            entity_id=request.entity_id,
            stock_code=request.stock_code,
        )
    )
    return SingleResponse(data=_create_view(run))


@router.get("/workflow-runs", response_model=ListResponse[WorkflowRunListItemView])
def list_workflow_runs(
    ticker: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    service: WorkflowOrchestrator = Depends(get_workflow_service),
) -> ListResponse[WorkflowRunListItemView]:
    rows, total = service.list_runs(ticker=ticker, status=status, limit=limit, offset=offset)
    return ListResponse(
        data=[_list_item_view(row) for row in rows],
        pagination=ListPagination(
            limit=limit,
            offset=offset,
            total=total,
            has_more=offset + len(rows) < total,
        ),
    )


@router.get("/workflow-runs/{workflow_run_id}", response_model=SingleResponse[WorkflowRunDetailView])
def get_workflow_run(
    workflow_run_id: str,
    service: WorkflowOrchestrator = Depends(get_workflow_service),
) -> SingleResponse[WorkflowRunDetailView]:
    run = _required_run(service, workflow_run_id)
    return SingleResponse(data=_detail_view(run))


@router.get("/workflow-runs/{workflow_run_id}/snapshot", response_model=SingleResponse[WorkflowSnapshotView])
def get_workflow_snapshot(
    workflow_run_id: str,
    include_raw_payload: bool = Query(False),
    include_events: bool = Query(False),
    max_evidence: int = Query(100, ge=0, le=500),
    max_arguments: int = Query(100, ge=0, le=500),
    service: WorkflowOrchestrator = Depends(get_workflow_service),
) -> SingleResponse[WorkflowSnapshotView]:
    del include_raw_payload
    try:
        snapshot = service.snapshot(
            workflow_run_id,
            include_events=include_events,
            max_evidence=max_evidence,
            max_arguments=max_arguments,
        )
    except KeyError:
        raise _not_found(workflow_run_id) from None
    return SingleResponse(data=_snapshot_view(snapshot))


@router.get("/workflow-runs/{workflow_run_id}/trace", response_model=SingleResponse[WorkflowTraceView])
def get_workflow_trace(
    workflow_run_id: str,
    service: WorkflowOrchestrator = Depends(get_workflow_service),
) -> SingleResponse[WorkflowTraceView]:
    run = _required_run(service, workflow_run_id)
    nodes, edges = service.trace(workflow_run_id)
    return SingleResponse(
        data=WorkflowTraceView(
            workflow_run_id=workflow_run_id,
            judgment_id=run.judgment_id,
            trace_nodes=[
                TraceNodeView(
                    node_type=node.node_type,  # type: ignore[arg-type]
                    node_id=node.node_id,
                    title=node.title,
                    summary=node.summary,
                )
                for node in nodes
            ],
            trace_edges=[
                TraceEdgeView(
                    from_node_id=edge.from_node_id,
                    to_node_id=edge.to_node_id,
                    edge_type=edge.edge_type,
                )
                for edge in edges
            ],
        )
    )


@router.get("/workflow-runs/{workflow_run_id}/events")
def stream_workflow_events(
    request: Request,
    workflow_run_id: str,
    after_sequence: int | None = Query(None),
    include_snapshot: bool = Query(False),
    follow: bool = Query(False),
    service: WorkflowOrchestrator = Depends(get_workflow_service),
) -> StreamingResponse:
    _required_run(service, workflow_run_id)

    async def iter_events() -> Any:
        last_sequence = after_sequence or 0
        if include_snapshot:
            snapshot = service.snapshot(workflow_run_id, max_evidence=20, max_arguments=20)
            payload = {
                "event_id": f"evt_{workflow_run_id}_snapshot",
                "workflow_run_id": workflow_run_id,
                "sequence": 0,
                "event_type": "snapshot",
                "created_at": datetime.now(UTC).isoformat(),
                "payload": _jsonable(_snapshot_view(snapshot).model_dump(exclude_none=True)),
        }
            yield _sse(payload)
        for event in service.list_events(workflow_run_id, after_sequence=after_sequence):
            last_sequence = max(last_sequence, event.sequence)
            yield _sse(_event_view(event).model_dump())
            if _is_terminal_event(event.event_type):
                return
        if _is_terminal_run(service, workflow_run_id):
            return
        while follow and not await request.is_disconnected():
            await asyncio.sleep(1)
            events = service.list_events(workflow_run_id, after_sequence=last_sequence)
            for event in events:
                last_sequence = max(last_sequence, event.sequence)
                yield _sse(_event_view(event).model_dump())
                if _is_terminal_event(event.event_type):
                    return
            if not events and _is_terminal_run(service, workflow_run_id):
                return

    return StreamingResponse(iter_events(), media_type="text/event-stream")


def _required_run(service: WorkflowOrchestrator, workflow_run_id: str) -> WorkflowRunRecord:
    run = service.get_run(workflow_run_id)
    if run is None:
        raise _not_found(workflow_run_id)
    return run


def _not_found(workflow_run_id: str) -> NotFoundError:
    return NotFoundError(
        f"Workflow run not found: {workflow_run_id}",
        code="WORKFLOW_RUN_NOT_FOUND",
        details={"workflow_run_id": workflow_run_id},
    )


def _is_terminal_event(event_type: str) -> bool:
    return event_type in {"workflow_completed", "workflow_failed"}


def _is_terminal_run(service: WorkflowOrchestrator, workflow_run_id: str) -> bool:
    run = service.get_run(workflow_run_id)
    return run is not None and run.status in {"completed", "failed", "cancelled"}


def _create_view(run: WorkflowRunRecord) -> WorkflowRunCreateView:
    return WorkflowRunCreateView(
        workflow_run_id=run.workflow_run_id,
        status=run.status,
        ticker=run.ticker,
        analysis_time=_dt(run.analysis_time),
        workflow_config_id=run.workflow_config_id,
        created_at=_dt(run.created_at),
        events_url=f"/api/v1/workflow-runs/{run.workflow_run_id}/events",
        snapshot_url=f"/api/v1/workflow-runs/{run.workflow_run_id}/snapshot",
        failure_code=run.failure_code,
        failure_message=run.failure_message,
    )


def _list_item_view(run: WorkflowRunRecord) -> WorkflowRunListItemView:
    return WorkflowRunListItemView(
        workflow_run_id=run.workflow_run_id,
        ticker=run.ticker,
        status=run.status,
        analysis_time=_dt(run.analysis_time),
        workflow_config_id=run.workflow_config_id,
        created_at=_dt(run.created_at),
        completed_at=_dt(run.completed_at) if run.completed_at else None,
        judgment_id=run.judgment_id,
        final_signal=run.final_signal,
        confidence=run.confidence,
    )


def _detail_view(run: WorkflowRunRecord) -> WorkflowRunDetailView:
    return WorkflowRunDetailView(
        workflow_run_id=run.workflow_run_id,
        ticker=run.ticker,
        status=run.status,
        stage=run.stage,
        analysis_time=_dt(run.analysis_time),
        workflow_config_id=run.workflow_config_id,
        created_at=_dt(run.created_at),
        started_at=_dt(run.started_at) if run.started_at else None,
        completed_at=_dt(run.completed_at) if run.completed_at else None,
        failure_code=run.failure_code,
        failure_message=run.failure_message,
        progress=WorkflowProgressView(
            raw_items_collected=run.progress.raw_items_collected,
            evidence_items_normalized=run.progress.evidence_items_normalized,
            evidence_items_structured=run.progress.evidence_items_structured,
            agent_arguments_completed=run.progress.agent_arguments_completed,
        ),
        links=WorkflowLinksView(
            events=f"/api/v1/workflow-runs/{run.workflow_run_id}/events",
            snapshot=f"/api/v1/workflow-runs/{run.workflow_run_id}/snapshot",
            trace=f"/api/v1/workflow-runs/{run.workflow_run_id}/trace",
            evidence=f"/api/v1/workflow-runs/{run.workflow_run_id}/evidence",
            judgment=f"/api/v1/workflow-runs/{run.workflow_run_id}/judgment",
        ),
    )


def _snapshot_view(snapshot: dict[str, Any]) -> WorkflowSnapshotView:
    run = snapshot["workflow_run"]
    return WorkflowSnapshotView(
        workflow_run=WorkflowSnapshotRunView(
            workflow_run_id=run.workflow_run_id,
            ticker=run.ticker,
            status=run.status,
            stage=run.stage,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
        ),
        evidence_items=[_evidence_view(item) for item in snapshot["evidence_items"]],
        agent_runs=[_agent_run_view(row) for row in snapshot["agent_runs"]],
        agent_arguments=[_argument_view(row) for row in snapshot["agent_arguments"]],
        round_summaries=[_round_summary_view(row) for row in snapshot["round_summaries"]],
        judgment=_judgment_view(snapshot["judgment"]) if snapshot["judgment"] else None,
        judge_tool_calls=[_tool_call_view(row) for row in snapshot["judge_tool_calls"]],
        last_event_sequence=snapshot["last_event_sequence"],
        events=[_event_view(row) for row in snapshot.get("events", [])] if "events" in snapshot else None,
    )


def _evidence_view(row: Any) -> EvidenceItemSnapshotView:
    return EvidenceItemSnapshotView(
        evidence_id=row.evidence_id,
        raw_ref=row.raw_ref,
        ticker=row.ticker,
        source=row.source,
        source_type=row.source_type,
        evidence_type=row.evidence_type,
        title=row.title,
        content=row.content,
        url=row.url,
        publish_time=_dt(row.publish_time) if row.publish_time else None,
        fetched_at=_dt(row.fetched_at) if row.fetched_at else None,
        source_quality=row.source_quality,
        relevance=row.relevance,
        freshness=row.freshness,
    )


def _agent_run_view(row: Any) -> AgentRunSnapshotView:
    return AgentRunSnapshotView(
        agent_run_id=row.agent_run_id,
        workflow_run_id=row.workflow_run_id,
        agent_id=row.agent_id,
        role=row.role,
        status=row.status,
        started_at=_dt(row.started_at),
        completed_at=_dt(row.completed_at) if row.completed_at else None,
        rounds=list(row.rounds),
    )


def _argument_view(row: Any) -> AgentArgumentSnapshotView:
    return AgentArgumentSnapshotView(
        agent_argument_id=row.agent_argument_id,
        agent_run_id=row.agent_run_id,
        workflow_run_id=row.workflow_run_id,
        agent_id=row.agent_id,
        role=row.role,
        round=row.round,
        argument=display_agent_argument_text(
            argument=row.argument,
            agent_id=row.agent_id,
            role=row.role,
            round_number=row.round,
            confidence=row.confidence,
            referenced_evidence_ids=row.referenced_evidence_ids,
            counter_evidence_ids=row.counter_evidence_ids,
        ),
        confidence=row.confidence,
        referenced_evidence_ids=list(row.referenced_evidence_ids),
        counter_evidence_ids=list(row.counter_evidence_ids),
        limitations=display_agent_limitations(row.limitations),
        role_output=sanitize_role_output_for_display(row.role_output),
        created_at=_dt(row.created_at) if row.created_at else None,
    )


def _round_summary_view(row: Any) -> RoundSummarySnapshotView:
    return RoundSummarySnapshotView(
        round_summary_id=row.round_summary_id,
        workflow_run_id=row.workflow_run_id,
        round=row.round,
        summary=display_round_summary_text(
            summary=row.summary,
            round_number=row.round,
            agent_argument_ids=row.agent_argument_ids,
            referenced_evidence_ids=row.referenced_evidence_ids,
            disputed_evidence_ids=row.disputed_evidence_ids,
        ),
        participants=list(row.participants),
        agent_argument_ids=list(row.agent_argument_ids),
        referenced_evidence_ids=list(row.referenced_evidence_ids),
        disputed_evidence_ids=list(row.disputed_evidence_ids),
        created_at=_dt(row.created_at) if row.created_at else None,
    )


def _judgment_view(row: Any) -> JudgmentSnapshotView:
    return JudgmentSnapshotView(
        judgment_id=row.judgment_id,
        workflow_run_id=row.workflow_run_id,
        final_signal=row.final_signal,
        confidence=row.confidence,
        time_horizon=row.time_horizon,
        key_positive_evidence_ids=list(row.key_positive_evidence_ids),
        key_negative_evidence_ids=list(row.key_negative_evidence_ids),
        reasoning=display_judgment_reasoning(
            reasoning=row.reasoning,
            final_signal=row.final_signal,
            confidence=row.confidence,
            positive_evidence_ids=row.key_positive_evidence_ids,
            negative_evidence_ids=row.key_negative_evidence_ids,
            referenced_agent_argument_ids=row.referenced_agent_argument_ids,
        ),
        risk_notes=display_chinese_notes(row.risk_notes, fallback="原始风险说明不是合规中文，需重新生成或补充中文说明。"),
        suggested_next_checks=display_chinese_notes(
            row.suggested_next_checks,
            fallback="原始后续核对项不是合规中文，需重新生成或补充中文说明。",
        ),
        referenced_agent_argument_ids=list(row.referenced_agent_argument_ids),
        limitations=display_chinese_notes(row.limitations, fallback="原始限制说明不是合规中文，需重新生成或补充中文说明。"),
        created_at=_dt(row.created_at) if row.created_at else None,
    )


def _tool_call_view(row: Any) -> JudgeToolCallSnapshotView:
    return JudgeToolCallSnapshotView(
        tool_call_id=row.tool_call_id,
        judgment_id=row.judgment_id,
        tool_name=row.tool_name,
        input=dict(row.input),
        output_summary=row.output_summary,
        referenced_evidence_ids=list(row.referenced_evidence_ids),
        created_at=_dt(row.created_at) if row.created_at else None,
    )


def _event_view(row: Any) -> WorkflowEventView:
    return WorkflowEventView(
        event_id=row.event_id,
        workflow_run_id=row.workflow_run_id,
        sequence=row.sequence,
        event_type=row.event_type,
        created_at=_dt(row.created_at),
        payload=dict(row.payload),
    )


def _sse(payload: dict[str, Any]) -> str:
    event_id = str(payload.get("event_id", ""))
    event_type = str(payload.get("event_type", "message"))
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_jsonable(child) for child in value]
    return value


def _dt(value: datetime) -> str:
    return value.isoformat()
