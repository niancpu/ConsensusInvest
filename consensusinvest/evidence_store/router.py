"""Evidence Web API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from consensusinvest.common.errors import NotFoundError
from consensusinvest.common.response import ListPagination, ListResponse, SingleResponse
from consensusinvest.evidence_store.client import EvidenceStoreClient
from consensusinvest.evidence_store.models import EvidenceQuery, EvidenceReferenceQuery
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.runtime.wiring import AppRuntime

from .models import EvidenceDetail, EvidenceItem, EvidenceReference, EvidenceStructure, RawItem
from .schemas import (
    EvidenceDetailView,
    EvidenceLinksView,
    EvidenceListItemView,
    EvidenceReferenceView,
    EvidenceStructureView,
    RawItemDetailView,
    RawItemListView,
)

router = APIRouter(prefix="/api/v1", tags=["evidence"])


def get_evidence_store(request: Request) -> EvidenceStoreClient:
    runtime: AppRuntime = request.app.state.runtime
    return runtime.evidence_store


@router.get("/workflow-runs/{workflow_run_id}/raw-items", response_model=ListResponse[RawItemListView])
def list_workflow_raw_items(
    workflow_run_id: str,
    source: str | None = Query(None),
    limit: int = Query(50, ge=0, le=200),
    offset: int = Query(0, ge=0),
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> ListResponse[RawItemListView]:
    rows = _workflow_raw_items(evidence_store, workflow_run_id, source=source)
    page = rows[offset : offset + limit]
    return ListResponse(
        data=[_raw_list_view(row) for row in page],
        pagination=_pagination(limit=limit, offset=offset, total=len(rows), returned=len(page)),
    )


@router.get("/raw-items/{raw_ref}", response_model=SingleResponse[RawItemDetailView])
def get_raw_item(
    raw_ref: str,
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> SingleResponse[RawItemDetailView]:
    raw = _required_raw(evidence_store, raw_ref)
    return SingleResponse(data=_raw_detail_view(evidence_store, raw))


@router.get("/workflow-runs/{workflow_run_id}/evidence", response_model=ListResponse[EvidenceListItemView])
def list_workflow_evidence(
    workflow_run_id: str,
    type: str | None = Query(None),  # noqa: A002 - query name fixed by API contract
    source_quality_min: float | None = Query(None, ge=0, le=1),
    limit: int = Query(50, ge=0, le=200),
    offset: int = Query(0, ge=0),
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> ListResponse[EvidenceListItemView]:
    page = evidence_store.query_evidence(
        _query_envelope(workflow_run_id=workflow_run_id),
        EvidenceQuery(
            workflow_run_id=workflow_run_id,
            evidence_types=(type,) if type else (),
            source_quality_min=source_quality_min,
            limit=limit,
            offset=offset,
        ),
    )
    return ListResponse(
        data=[_evidence_list_view(evidence_store, item, _detail_or_none(evidence_store, item.evidence_id)) for item in page.items],
        pagination=_pagination(limit=limit, offset=offset, total=page.total, returned=len(page.items)),
    )


@router.get("/evidence/{evidence_id}", response_model=SingleResponse[EvidenceDetailView])
def get_evidence(
    evidence_id: str,
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> SingleResponse[EvidenceDetailView]:
    detail = _required_evidence(evidence_store, evidence_id)
    return SingleResponse(data=_evidence_detail_view(evidence_store, detail))


@router.get("/evidence/{evidence_id}/structure", response_model=SingleResponse[EvidenceStructureView])
def get_evidence_structure(
    evidence_id: str,
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> SingleResponse[EvidenceStructureView]:
    detail = _required_evidence(evidence_store, evidence_id)
    if detail.structure is None:
        raise NotFoundError(
            f"Evidence structure not found: {evidence_id}",
            code="EVIDENCE_STRUCTURE_NOT_FOUND",
            details={"evidence_id": evidence_id},
        )
    return SingleResponse(data=_structure_view(detail.evidence, detail.structure))


@router.get("/evidence/{evidence_id}/raw", response_model=SingleResponse[RawItemDetailView])
def get_evidence_raw(
    evidence_id: str,
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> SingleResponse[RawItemDetailView]:
    detail = _required_evidence(evidence_store, evidence_id)
    raw = _required_raw(evidence_store, detail.raw_ref)
    return SingleResponse(data=_raw_detail_view(evidence_store, raw))


@router.get("/evidence/{evidence_id}/references", response_model=ListResponse[EvidenceReferenceView])
def list_evidence_references(
    evidence_id: str,
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> ListResponse[EvidenceReferenceView]:
    _required_evidence(evidence_store, evidence_id)
    rows = evidence_store.query_references(
        _query_envelope(),
        EvidenceReferenceQuery(evidence_id=evidence_id, limit=500, offset=0),
    )
    return _reference_response(rows)


@router.get(
    "/workflow-runs/{workflow_run_id}/evidence-references",
    response_model=ListResponse[EvidenceReferenceView],
)
def list_workflow_evidence_references(
    workflow_run_id: str,
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> ListResponse[EvidenceReferenceView]:
    rows = evidence_store.query_references(
        _query_envelope(workflow_run_id=workflow_run_id),
        EvidenceReferenceQuery(workflow_run_id=workflow_run_id, limit=500, offset=0),
    )
    return _reference_response(rows)


def _workflow_raw_items(
    evidence_store: EvidenceStoreClient,
    workflow_run_id: str,
    *,
    source: str | None,
) -> list[RawItem]:
    page = evidence_store.query_evidence(
        _query_envelope(workflow_run_id=workflow_run_id),
        EvidenceQuery(workflow_run_id=workflow_run_id, sources=(source,) if source else (), limit=1000),
    )
    rows: list[RawItem] = []
    for item in page.items:
        try:
            rows.append(evidence_store.get_raw(_query_envelope(workflow_run_id=workflow_run_id), item.raw_ref))
        except KeyError:
            continue
    return rows


def _required_evidence(evidence_store: EvidenceStoreClient, evidence_id: str) -> EvidenceDetail:
    try:
        return evidence_store.get_evidence(_query_envelope(), evidence_id)
    except KeyError:
        raise NotFoundError(
            f"Evidence not found: {evidence_id}",
            code="EVIDENCE_NOT_FOUND",
            details={"evidence_id": evidence_id},
        ) from None


def _required_raw(evidence_store: EvidenceStoreClient, raw_ref: str) -> RawItem:
    try:
        return evidence_store.get_raw(_query_envelope(), raw_ref)
    except KeyError:
        raise NotFoundError(
            f"Raw item not found: {raw_ref}",
            code="RAW_ITEM_NOT_FOUND",
            details={"raw_ref": raw_ref},
        ) from None


def _detail_or_none(evidence_store: EvidenceStoreClient, evidence_id: str) -> EvidenceDetail | None:
    try:
        return evidence_store.get_evidence(_query_envelope(), evidence_id)
    except KeyError:
        return None


def _raw_list_view(row: RawItem) -> RawItemListView:
    return RawItemListView(
        raw_ref=row.raw_ref,
        workflow_run_id=_workflow_run_id(row),
        source=row.source,
        source_type=row.source_type,
        ticker=row.ticker,
        title=row.title,
        publish_time=_dt(row.publish_time),
        fetched_at=_dt(row.fetched_at),
        url=row.url,
        payload_preview=_payload_preview(row.raw_payload),
    )


def _raw_detail_view(evidence_store: EvidenceStoreClient, row: RawItem) -> RawItemDetailView:
    return RawItemDetailView(
        raw_ref=row.raw_ref,
        workflow_run_id=_workflow_run_id(row),
        source=row.source,
        source_type=row.source_type,
        ticker=row.ticker,
        title=row.title,
        content=row.content,
        url=row.url,
        publish_time=_dt(row.publish_time),
        fetched_at=_dt(row.fetched_at),
        raw_payload=dict(row.raw_payload),
        derived_evidence_ids=_derived_evidence_ids(evidence_store, row.raw_ref),
    )


def _evidence_list_view(
    evidence_store: EvidenceStoreClient,
    item: EvidenceItem,
    detail: EvidenceDetail | None,
) -> EvidenceListItemView:
    structure = detail.structure if detail is not None else None
    return EvidenceListItemView(
        evidence_id=item.evidence_id,
        workflow_run_id=_evidence_workflow_run_id(evidence_store, item),
        ticker=item.ticker,
        source=item.source,
        source_type=item.source_type,
        evidence_type=item.evidence_type,
        title=item.title,
        objective_summary=structure.objective_summary if structure else None,
        publish_time=_dt(item.publish_time),
        fetched_at=_dt(item.fetched_at),
        source_quality=item.source_quality,
        relevance=item.relevance,
        freshness=item.freshness,
        structuring_confidence=structure.structuring_confidence if structure else None,
        quality_notes=list(structure.quality_notes if structure else item.quality_notes),
        raw_ref=item.raw_ref,
    )


def _evidence_detail_view(evidence_store: EvidenceStoreClient, detail: EvidenceDetail) -> EvidenceDetailView:
    item = detail.evidence
    structure = detail.structure
    return EvidenceDetailView(
        evidence_id=item.evidence_id,
        workflow_run_id=_evidence_workflow_run_id(evidence_store, item),
        ticker=item.ticker,
        source=item.source,
        source_type=item.source_type,
        evidence_type=item.evidence_type,
        title=item.title,
        content=item.content,
        url=item.url,
        publish_time=_dt(item.publish_time),
        fetched_at=_dt(item.fetched_at),
        entities=list(item.entity_ids),
        tags=[item.evidence_type] if item.evidence_type else [],
        objective_summary=structure.objective_summary if structure else None,
        key_facts=list(structure.key_facts) if structure else [],
        claims=list(structure.claims) if structure else [],
        source_quality=item.source_quality,
        relevance=item.relevance,
        freshness=item.freshness,
        structuring_confidence=structure.structuring_confidence if structure else None,
        quality_notes=list(structure.quality_notes if structure else item.quality_notes),
        raw_ref=detail.raw_ref,
        links=EvidenceLinksView(
            structure=f"/api/v1/evidence/{item.evidence_id}/structure",
            raw=f"/api/v1/evidence/{item.evidence_id}/raw",
            references=f"/api/v1/evidence/{item.evidence_id}/references",
        ),
    )


def _structure_view(item: EvidenceItem, structure: EvidenceStructure) -> EvidenceStructureView:
    return EvidenceStructureView(
        evidence_structure_id=structure.structure_id,
        evidence_id=structure.evidence_id,
        objective_summary=structure.objective_summary,
        key_facts=list(structure.key_facts),
        claims=list(structure.claims),
        source_quality=item.source_quality,
        relevance=item.relevance,
        freshness=item.freshness,
        structuring_confidence=structure.structuring_confidence,
        quality_notes=list(structure.quality_notes),
        created_by_agent_id=structure.created_by_agent_id,
        created_at=_dt(structure.created_at),
    )


def _reference_response(rows: list[EvidenceReference]) -> ListResponse[EvidenceReferenceView]:
    views = [
        EvidenceReferenceView(
            reference_id=row.reference_id,
            workflow_run_id=row.workflow_run_id,
            source_type=row.source_type,
            source_id=row.source_id,
            evidence_id=row.evidence_id,
            reference_role=row.reference_role,
            round=row.round,
            created_at=_dt(row.created_at),
        )
        for row in rows
    ]
    return ListResponse(
        data=views,
        pagination=ListPagination(limit=len(views), offset=0, total=len(views), has_more=False),
    )


def _derived_evidence_ids(evidence_store: EvidenceStoreClient, raw_ref: str) -> list[str]:
    page = evidence_store.query_evidence(_query_envelope(), EvidenceQuery(limit=1000))
    return [item.evidence_id for item in page.items if item.raw_ref == raw_ref]


def _payload_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(list(payload.items())[:5])


def _evidence_workflow_run_id(evidence_store: EvidenceStoreClient, item: EvidenceItem) -> str | None:
    try:
        return _workflow_run_id(evidence_store.get_raw(_query_envelope(), item.raw_ref))
    except KeyError:
        return None


def _workflow_run_id(raw: RawItem) -> str | None:
    value = raw.ingest_context.get("workflow_run_id")
    return str(value) if value is not None else None


def _pagination(*, limit: int, offset: int, total: int, returned: int) -> ListPagination:
    return ListPagination(limit=limit, offset=offset, total=total, has_more=offset + returned < total)


def _query_envelope(*, workflow_run_id: str | None = None) -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="req_evidence_api_query",
        correlation_id="corr_evidence_api_query",
        workflow_run_id=workflow_run_id,
        analysis_time=datetime.now(timezone.utc),
        requested_by="evidence_api",
    )


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
