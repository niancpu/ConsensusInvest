"""Agent/Judgment API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from consensusinvest.common.errors import NotFoundError
from consensusinvest.common.response import ListPagination, ListResponse, SingleResponse
from consensusinvest.runtime.wiring import AppRuntime

from .models import (
    AgentArgumentRecord,
    AgentRunRecord,
    JudgeToolCallRecord,
    JudgmentRecord,
    RoundSummaryRecord,
)
from .repository import InMemoryAgentSwarmRepository
from .schemas import (
    AgentArgumentView,
    AgentRunView,
    EvidenceReferenceView,
    JudgmentLinks,
    JudgmentView,
    JudgeToolCallView,
    RoundSummaryView,
)

router = APIRouter(prefix="/api/v1", tags=["agents_judgments"])


def get_agent_repository(request: Request) -> InMemoryAgentSwarmRepository:
    runtime: AppRuntime = request.app.state.runtime
    return runtime.agent_repository


@router.get(
    "/workflow-runs/{workflow_run_id}/agent-runs",
    response_model=ListResponse[AgentRunView],
)
def list_agent_runs(
    workflow_run_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> ListResponse[AgentRunView]:
    rows = [_agent_run_view(row) for row in repository.list_agent_runs(workflow_run_id)]
    return _list_response(rows)


@router.get(
    "/workflow-runs/{workflow_run_id}/agent-arguments",
    response_model=ListResponse[AgentArgumentView],
)
def list_agent_arguments(
    workflow_run_id: str,
    agent_id: str | None = Query(None),
    round: int | None = Query(None),  # noqa: A002 - field fixed by API contract
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> ListResponse[AgentArgumentView]:
    rows = [
        _argument_view(row)
        for row in repository.list_arguments(
            workflow_run_id,
            agent_id=agent_id,
            round=round,
        )
    ]
    return _list_response(rows)


@router.get(
    "/agent-arguments/{agent_argument_id}",
    response_model=SingleResponse[AgentArgumentView],
)
def get_agent_argument(
    agent_argument_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> SingleResponse[AgentArgumentView]:
    argument = repository.get_argument(agent_argument_id)
    if argument is None:
        raise NotFoundError(
            f"Agent argument not found: {agent_argument_id}",
            code="AGENT_ARGUMENT_NOT_FOUND",
            details={"agent_argument_id": agent_argument_id},
        )
    return SingleResponse(data=_argument_view(argument))


@router.get(
    "/agent-arguments/{agent_argument_id}/references",
    response_model=ListResponse[EvidenceReferenceView],
)
def list_agent_argument_references(
    agent_argument_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> ListResponse[EvidenceReferenceView]:
    if repository.get_argument(agent_argument_id) is None:
        raise NotFoundError(
            f"Agent argument not found: {agent_argument_id}",
            code="AGENT_ARGUMENT_NOT_FOUND",
            details={"agent_argument_id": agent_argument_id},
        )
    rows = [
        EvidenceReferenceView(
            reference_id=ref.reference_id,
            source_type=ref.source_type,
            source_id=ref.source_id,
            evidence_id=ref.evidence_id,
            reference_role=ref.reference_role,
            round=ref.round,
        )
        for ref in repository.list_references(
            source_type="agent_argument",
            source_id=agent_argument_id,
        )
    ]
    return _list_response(rows)


@router.get(
    "/workflow-runs/{workflow_run_id}/round-summaries",
    response_model=ListResponse[RoundSummaryView],
)
def list_round_summaries(
    workflow_run_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> ListResponse[RoundSummaryView]:
    rows = [_round_summary_view(row) for row in repository.list_round_summaries(workflow_run_id)]
    return _list_response(rows)


@router.get(
    "/round-summaries/{round_summary_id}",
    response_model=SingleResponse[RoundSummaryView],
)
def get_round_summary(
    round_summary_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> SingleResponse[RoundSummaryView]:
    summary = repository.get_round_summary(round_summary_id)
    if summary is None:
        raise NotFoundError(
            f"Round summary not found: {round_summary_id}",
            code="ROUND_SUMMARY_NOT_FOUND",
            details={"round_summary_id": round_summary_id},
        )
    return SingleResponse(data=_round_summary_view(summary))


@router.get(
    "/workflow-runs/{workflow_run_id}/judgment",
    response_model=SingleResponse[JudgmentView],
)
def get_workflow_judgment(
    workflow_run_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> SingleResponse[JudgmentView]:
    judgment = repository.get_judgment_by_workflow(workflow_run_id)
    if judgment is None:
        raise NotFoundError(
            f"Judgment not found for workflow run: {workflow_run_id}",
            code="JUDGMENT_NOT_FOUND",
            details={"workflow_run_id": workflow_run_id},
        )
    return SingleResponse(data=_judgment_view(repository, judgment))


@router.get("/judgments/{judgment_id}", response_model=SingleResponse[JudgmentView])
def get_judgment(
    judgment_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> SingleResponse[JudgmentView]:
    judgment = repository.get_judgment(judgment_id)
    if judgment is None:
        raise NotFoundError(
            f"Judgment not found: {judgment_id}",
            code="JUDGMENT_NOT_FOUND",
            details={"judgment_id": judgment_id},
        )
    return SingleResponse(data=_judgment_view(repository, judgment))


@router.get(
    "/judgments/{judgment_id}/references",
    response_model=ListResponse[EvidenceReferenceView],
)
def list_judgment_references(
    judgment_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> ListResponse[EvidenceReferenceView]:
    if repository.get_judgment(judgment_id) is None:
        raise NotFoundError(
            f"Judgment not found: {judgment_id}",
            code="JUDGMENT_NOT_FOUND",
            details={"judgment_id": judgment_id},
        )
    rows = [
        EvidenceReferenceView(
            reference_id=ref.reference_id,
            source_type=ref.source_type,
            source_id=ref.source_id,
            evidence_id=ref.evidence_id,
            reference_role=ref.reference_role,
            round=ref.round,
        )
        for ref in repository.list_references(source_type="judgment", source_id=judgment_id)
    ]
    return _list_response(rows)


@router.get(
    "/judgments/{judgment_id}/tool-calls",
    response_model=ListResponse[JudgeToolCallView],
)
def list_judge_tool_calls(
    judgment_id: str,
    repository: InMemoryAgentSwarmRepository = Depends(get_agent_repository),
) -> ListResponse[JudgeToolCallView]:
    if repository.get_judgment(judgment_id) is None:
        raise NotFoundError(
            f"Judgment not found: {judgment_id}",
            code="JUDGMENT_NOT_FOUND",
            details={"judgment_id": judgment_id},
        )
    rows = [_tool_call_view(row) for row in repository.list_tool_calls(judgment_id)]
    return _list_response(rows)


def _list_response(rows: list) -> ListResponse:
    return ListResponse(
        data=rows,
        pagination=ListPagination(limit=len(rows), offset=0, total=len(rows), has_more=False),
    )


def _agent_run_view(row: AgentRunRecord) -> AgentRunView:
    return AgentRunView(
        agent_run_id=row.agent_run_id,
        workflow_run_id=row.workflow_run_id,
        agent_id=row.agent_id,
        role=row.role,
        status=row.status,
        started_at=_dt(row.started_at),
        completed_at=_dt(row.completed_at) if row.completed_at else None,
        rounds=list(row.rounds),
    )


def _argument_view(row: AgentArgumentRecord) -> AgentArgumentView:
    return AgentArgumentView(
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
        created_at=_dt(row.created_at),
    )


def _round_summary_view(row: RoundSummaryRecord) -> RoundSummaryView:
    return RoundSummaryView(
        round_summary_id=row.round_summary_id,
        workflow_run_id=row.workflow_run_id,
        round=row.round,
        summary=row.summary,
        participants=list(row.participants),
        agent_argument_ids=list(row.agent_argument_ids),
        referenced_evidence_ids=list(row.referenced_evidence_ids),
        disputed_evidence_ids=list(row.disputed_evidence_ids),
        created_at=_dt(row.created_at),
    )


def _judgment_view(repository: InMemoryAgentSwarmRepository, row: JudgmentRecord) -> JudgmentView:
    tool_call_count = len(repository.list_tool_calls(row.judgment_id))
    return JudgmentView(
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
        tool_call_count=tool_call_count,
        created_at=_dt(row.created_at),
        links=JudgmentLinks(
            references=f"/api/v1/judgments/{row.judgment_id}/references",
            trace=f"/api/v1/workflow-runs/{row.workflow_run_id}/trace",
        ),
    )


def _tool_call_view(row: JudgeToolCallRecord) -> JudgeToolCallView:
    return JudgeToolCallView(
        tool_call_id=row.tool_call_id,
        judgment_id=row.judgment_id,
        tool_name=row.tool_name,
        input=dict(row.input),
        output_summary=row.output_summary,
        referenced_evidence_ids=list(row.referenced_evidence_ids),
        used_for=row.used_for,
        created_at=_dt(row.created_at),
    )


def _dt(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
