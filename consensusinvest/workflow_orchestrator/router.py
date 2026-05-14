"""Workflow API routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from consensusinvest.agent_swarm import AgentSwarmRuntime, JudgeRuntime, InMemoryAgentSwarmRepository
from consensusinvest.common.errors import NotFoundError
from consensusinvest.common.response import ListPagination, ListResponse, SingleResponse
from consensusinvest.evidence_store import FakeEvidenceStoreClient

from .models import WorkflowOptions, WorkflowQuery, WorkflowRunCreate, WorkflowRunRecord
from .repository import InMemoryWorkflowRepository
from .schemas import (
    AgentArgumentSnapshotView,
    AgentRunSnapshotView,
    EvidenceItemSnapshotView,
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

_evidence_store = FakeEvidenceStoreClient()
_agent_repository = InMemoryAgentSwarmRepository()
_agent_swarm = AgentSwarmRuntime(evidence_store=_evidence_store, repository=_agent_repository)
_judge = JudgeRuntime(evidence_store=_evidence_store, repository=_agent_repository)
service = WorkflowOrchestrator(
    repository=InMemoryWorkflowRepository(),
    evidence_store=_evidence_store,
    agent_swarm=_agent_swarm,
    judge=_judge,
)


@router.post("/workflow-runs", status_code=202, response_model=SingleResponse[WorkflowRunCreateView])
def create_workflow_run(request: WorkflowRunCreateRequest) -> SingleResponse[WorkflowRunCreateView]:
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
def get_workflow_run(workflow_run_id: str) -> SingleResponse[WorkflowRunDetailView]:
    run = _required_run(workflow_run_id)
    return SingleResponse(data=_detail_view(run))


@router.get("/workflow-runs/{workflow_run_id}/snapshot", response_model=SingleResponse[WorkflowSnapshotView])
def get_workflow_snapshot(
    workflow_run_id: str,
    include_raw_payload: bool = Query(False),
    include_events: bool = Query(False),
    max_evidence: int = Query(100, ge=0, le=500),
    max_arguments: int = Query(100, ge=0, le=500),
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
def get_workflow_trace(workflow_run_id: str) -> SingleResponse[WorkflowTraceView]:
    run = _required_run(workflow_run_id)
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
    workflow_run_id: str,
    after_sequence: int | None = Query(None),
    include_snapshot: bool = Query(False),
) -> StreamingResponse:
    _required_run(workflow_run_id)

    def iter_events() -> Any:
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
            yield _sse(_event_view(event).model_dump())

    return StreamingResponse(iter_events(), media_type="text/event-stream")


def _required_run(workflow_run_id: str) -> WorkflowRunRecord:
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
        ),
        evidence_items=[_evidence_view(item) for item in snapshot["evidence_items"]],
        agent_runs=[_agent_run_view(row) for row in snapshot["agent_runs"]],
        agent_arguments=[_argument_view(row) for row in snapshot["agent_arguments"]],
        round_summaries=[_round_summary_view(row) for row in snapshot["round_summaries"]],
        judgment=_judgment_view(snapshot["judgment"]) if snapshot["judgment"] else None,
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
        argument=row.argument,
        confidence=row.confidence,
        referenced_evidence_ids=list(row.referenced_evidence_ids),
        counter_evidence_ids=list(row.counter_evidence_ids),
        limitations=list(row.limitations),
        role_output=dict(row.role_output),
        created_at=_dt(row.created_at) if row.created_at else None,
    )


def _round_summary_view(row: Any) -> RoundSummarySnapshotView:
    return RoundSummarySnapshotView(
        round_summary_id=row.round_summary_id,
        workflow_run_id=row.workflow_run_id,
        round=row.round,
        summary=row.summary,
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
        reasoning=row.reasoning,
        risk_notes=list(row.risk_notes),
        suggested_next_checks=list(row.suggested_next_checks),
        referenced_agent_argument_ids=list(row.referenced_agent_argument_ids),
        limitations=list(row.limitations),
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
