"""Evidence, entity, and judgment projection helpers for Report Module views."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from consensusinvest.agent_swarm.models import JudgmentRecord
from consensusinvest.common.errors import NotFoundError
from consensusinvest.entities.repository import EntityRecord, EntityRelationRecord
from consensusinvest.evidence_store.client import EvidenceStoreClient
from consensusinvest.evidence_store.models import EvidenceDetail, EvidenceItem, EvidenceQuery

from .schemas import RiskItem
from ._utils import _comparable_dt, _query_envelope
from .projections import _stock_code, _ticker

def _selected_judgment(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    *,
    workflow_run_id: str | None,
    latest: bool,
) -> JudgmentRecord | None:
    if workflow_run_id:
        judgment = reader.judgment_by_workflow(workflow_run_id)
        if judgment is None:
            raise NotFoundError(
                f"Workflow run not found: {workflow_run_id}",
                code="WORKFLOW_NOT_FOUND",
                details={"workflow_run_id": workflow_run_id},
            )
        return judgment
    if latest:
        return reader.latest_judgment_for_entity(entity.entity_id)
    return None

def _required_stock(reader: ReportRuntimeReader, stock_code: str) -> EntityRecord:
    entity = reader.find_entity_by_stock_code(stock_code)
    if entity is None or _stock_code(entity) is None:
        raise NotFoundError(f"Stock not found: {stock_code}", details={"stock_code": stock_code})
    return entity

def _industry_relation(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
) -> tuple[EntityRelationRecord | None, EntityRecord | None]:
    relation_types = {"belongs_to_industry", "industry", "in_industry", "has_company"}
    for relation in reader.entity_repository.list_relations(entity.entity_id, depth=1):
        if relation.relation_type not in relation_types:
            continue
        other_id = relation.to_entity_id if relation.from_entity_id == entity.entity_id else relation.from_entity_id
        other = _entity_by_id(reader.entity_repository, other_id)
        if other is not None and other.entity_type == "industry":
            return relation, other
    return None, None

def _industry_evidence(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    relation: EntityRelationRecord,
    industry: EntityRecord,
    *,
    workflow_run_id: str | None,
) -> list[EvidenceDetail]:
    details_by_id: dict[str, EvidenceDetail] = {}
    for evidence_id in relation.evidence_ids:
        detail = _detail_by_id(reader.evidence_store, evidence_id)
        if detail is not None:
            details_by_id[detail.evidence.evidence_id] = detail
    for detail in [
        *reader.evidence_for_entity(industry.entity_id, limit=20),
        *reader.evidence_for_entity(entity.entity_id, limit=20),
    ]:
        item = detail.evidence
        if workflow_run_id is not None and not _detail_matches_workflow(detail, workflow_run_id):
            continue
        if item.evidence_type in {"industry_news", "policy", "company_news", "financial_report", "risk_disclosure"}:
            details_by_id[item.evidence_id] = detail
    return sorted(details_by_id.values(), key=_detail_sort_key, reverse=True)

def _event_evidence(
    reader: ReportRuntimeReader,
    entity: EntityRecord,
    *,
    workflow_run_id: str | None,
    limit: int,
) -> list[EvidenceDetail]:
    event_types = (
        "company_news",
        "industry_news",
        "announcement",
        "financial_report",
        "policy",
        "macro_event",
        "market_event",
    )
    page = reader.evidence_store.query_evidence(
        _query_envelope(),
        EvidenceQuery(
            ticker=_ticker(entity),
            entity_ids=(entity.entity_id,),
            workflow_run_id=workflow_run_id,
            evidence_types=event_types,
            limit=limit * 4,
            offset=0,
        ),
    )
    details = [_detail_or_item(reader.evidence_store, item) for item in page.items]
    details.sort(key=lambda detail: (_event_score(detail), *_detail_sort_key(detail)), reverse=True)
    return details[:limit]

def _detail_by_id(evidence_store: EvidenceStoreClient, evidence_id: str) -> EvidenceDetail | None:
    try:
        return evidence_store.get_evidence(_query_envelope(), evidence_id)
    except KeyError:
        return None

def _detail_matches_workflow(detail: EvidenceDetail, workflow_run_id: str) -> bool:
    return any(ref.workflow_run_id == workflow_run_id for ref in detail.references)

def _detail_sort_key(detail: EvidenceDetail) -> tuple[datetime, str]:
    return (_comparable_dt(detail.evidence.publish_time), detail.evidence.evidence_id)

def _industry_text(
    records: list[EvidenceDetail],
    *,
    fact_names: tuple[str, ...],
    keywords: tuple[str, ...],
    fallback: str,
) -> str:
    fact = _first_fact_text(records, fact_names)
    if fact is not None:
        return fact
    keyword_text = _first_keyword_summary(records, keywords)
    if keyword_text is not None:
        return keyword_text
    return fallback

def _first_fact_text(records: list[EvidenceDetail], names: tuple[str, ...]) -> str | None:
    normalized_names = {name.lower() for name in names}
    for detail in records:
        structure = detail.structure
        if structure is None:
            continue
        for fact in structure.key_facts:
            name = str(fact.get("name") or "").strip().lower()
            if name not in normalized_names:
                continue
            value = str(fact.get("value") or "").strip()
            unit = str(fact.get("unit") or "").strip()
            if value:
                return f"{value}{unit}"
    return None

def _first_keyword_summary(records: list[EvidenceDetail], keywords: tuple[str, ...]) -> str | None:
    for detail in records:
        text = _summary(detail).strip()
        if text and any(keyword in text for keyword in keywords):
            return text
    return None

def _policy_support_level(records: list[EvidenceDetail]) -> str:
    fact = _first_fact_text(records, ("policy_support_level", "政策支持等级"))
    if fact in {"low", "medium", "high"}:
        return fact
    if _first_keyword_summary(records, ("大力支持", "强支持", "重点支持", "政策支持力度较强")) is not None:
        return "high"
    if _first_keyword_summary(records, ("政策", "支持", "补贴", "规划")) is not None:
        return "medium"
    return "low"

def _event_name(detail: EvidenceDetail) -> str:
    structure = detail.structure
    if structure is not None:
        for fact in structure.key_facts:
            name = str(fact.get("name") or "").strip().lower()
            if name in {"event_name", "event", "事件"}:
                value = str(fact.get("value") or "").strip()
                if value:
                    return value
    item = detail.evidence
    return item.title or _summary(detail)[:80] or item.evidence_id

def _event_score(detail: EvidenceDetail) -> int:
    item = detail.evidence
    quality = item.source_quality if item.source_quality is not None else 0.5
    relevance = item.relevance if item.relevance is not None else 0.5
    freshness = item.freshness if item.freshness is not None else 0.5
    score = int(round((quality * 0.4 + relevance * 0.4 + freshness * 0.2) * 100))
    return max(0, min(score, 100))

def _event_level(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"

def _entity_by_id(repository: Any, entity_id: str) -> EntityRecord | None:
    getter = getattr(repository, "get_entity", None)
    if callable(getter):
        return getter(entity_id)
    rows, _ = repository.list_entities(limit=1000, offset=0)
    for row in rows:
        if row.entity_id == entity_id:
            return row
    return None

def _detail_or_item(evidence_store: EvidenceStoreClient, item: EvidenceItem) -> EvidenceDetail:
    try:
        return evidence_store.get_evidence(_query_envelope(), item.evidence_id)
    except KeyError:
        return EvidenceDetail(evidence=item, structure=None, raw_ref=item.raw_ref, references=[])

def _risk_disclosures(records: list[EvidenceDetail]) -> list[RiskItem]:
    risks: list[RiskItem] = []
    for detail in records:
        item = detail.evidence
        if item.evidence_type != "risk_disclosure":
            continue
        risks.append(
            RiskItem(
                text=_summary(detail),
                evidence_ids=[item.evidence_id],
                source="evidence_structure_risk_disclosure",
            )
        )
    return risks

def _summary(detail: EvidenceDetail) -> str:
    if detail.structure is not None:
        return detail.structure.objective_summary
    item = detail.evidence
    return item.content or item.title or item.evidence_id
