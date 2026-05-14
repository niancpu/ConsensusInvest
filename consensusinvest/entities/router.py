"""Entity Web API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request

from consensusinvest.common.errors import NotFoundError
from consensusinvest.common.response import ListPagination, ListResponse, SingleResponse
from consensusinvest.entities.repository import EntityRecord, EntityRelationRecord, InMemoryEntityRepository
from consensusinvest.evidence_store.models import EvidenceItem, EvidenceQuery
from consensusinvest.evidence_store.router import get_evidence_store, _detail_or_none, _evidence_list_view
from consensusinvest.evidence_store.client import EvidenceStoreClient
from consensusinvest.runtime import InternalCallEnvelope
from consensusinvest.runtime.wiring import AppRuntime

from .schemas import EntityEvidenceListItemView, EntityRelationView, EntityView

router = APIRouter(prefix="/api/v1", tags=["entities"])


def get_entity_repository(request: Request) -> InMemoryEntityRepository:
    runtime: AppRuntime = request.app.state.runtime
    return runtime.entity_repository


@router.get("/entities", response_model=ListResponse[EntityView])
def list_entities(
    query: str | None = Query(None),
    type: str | None = Query(None),  # noqa: A002 - query name fixed by API contract
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    repository: InMemoryEntityRepository = Depends(get_entity_repository),
) -> ListResponse[EntityView]:
    rows, total = repository.list_entities(query=query, entity_type=type, limit=limit, offset=offset)
    return ListResponse(
        data=[_entity_view(row) for row in rows],
        pagination=ListPagination(limit=limit, offset=offset, total=total, has_more=offset + len(rows) < total),
    )


@router.get("/entities/{entity_id}", response_model=SingleResponse[EntityView])
def get_entity(
    entity_id: str,
    repository: InMemoryEntityRepository = Depends(get_entity_repository),
) -> SingleResponse[EntityView]:
    return SingleResponse(data=_entity_view(_required_entity(repository, entity_id)))


@router.get("/entities/{entity_id}/evidence", response_model=ListResponse[EntityEvidenceListItemView])
def list_entity_evidence(
    entity_id: str,
    limit: int = Query(50, ge=0, le=200),
    offset: int = Query(0, ge=0),
    repository: InMemoryEntityRepository = Depends(get_entity_repository),
    evidence_store: EvidenceStoreClient = Depends(get_evidence_store),
) -> ListResponse[EntityEvidenceListItemView]:
    _required_entity(repository, entity_id)
    page = evidence_store.query_evidence(
        _query_envelope(),
        EvidenceQuery(entity_ids=(entity_id,), limit=limit, offset=offset),
    )
    return ListResponse(
        data=[_entity_evidence_view(evidence_store, item) for item in page.items],
        pagination=ListPagination(
            limit=limit,
            offset=offset,
            total=page.total,
            has_more=offset + len(page.items) < page.total,
        ),
    )


@router.get("/entities/{entity_id}/relations", response_model=ListResponse[EntityRelationView])
def list_entity_relations(
    entity_id: str,
    depth: int = Query(1, ge=1, le=1),
    repository: InMemoryEntityRepository = Depends(get_entity_repository),
) -> ListResponse[EntityRelationView]:
    _required_entity(repository, entity_id)
    rows = repository.list_relations(entity_id, depth=depth)
    return ListResponse(
        data=[_relation_view(row) for row in rows],
        pagination=ListPagination(limit=len(rows), offset=0, total=len(rows), has_more=False),
    )


def _required_entity(repository: InMemoryEntityRepository, entity_id: str) -> EntityRecord:
    row = repository.get_entity(entity_id)
    if row is None:
        raise NotFoundError(
            f"Entity not found: {entity_id}",
            code="ENTITY_NOT_FOUND",
            details={"entity_id": entity_id},
        )
    return row


def _entity_view(row: EntityRecord) -> EntityView:
    return EntityView(
        entity_id=row.entity_id,
        entity_type=row.entity_type,
        name=row.name,
        aliases=list(row.aliases),
        description=row.description,
    )


def _entity_evidence_view(
    evidence_store: EvidenceStoreClient,
    item: EvidenceItem,
) -> EntityEvidenceListItemView:
    return EntityEvidenceListItemView(
        **_evidence_list_view(
            evidence_store,
            item,
            _detail_or_none(evidence_store, item.evidence_id),
        ).model_dump()
    )


def _relation_view(row: EntityRelationRecord) -> EntityRelationView:
    return EntityRelationView(
        relation_id=row.relation_id,
        from_entity_id=row.from_entity_id,
        to_entity_id=row.to_entity_id,
        relation_type=row.relation_type,
        weight=row.weight,
        evidence_ids=list(row.evidence_ids),
    )


def _query_envelope() -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="req_entity_api_query",
        correlation_id="corr_entity_api_query",
        workflow_run_id=None,
        analysis_time=datetime.now(timezone.utc),
        requested_by="entity_api",
    )
