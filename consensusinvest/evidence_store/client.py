"""Evidence Store protocol and stdlib-only in-memory implementation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar

from consensusinvest.evidence_normalizer.service import EvidenceNormalizer
from consensusinvest.evidence_normalizer.models import NormalizedEvidenceDraft
from consensusinvest.evidence_store.models import (
    EvidenceDetail,
    EvidenceItem,
    EvidencePage,
    EvidenceQuery,
    EvidenceReference,
    EvidenceReferenceBatch,
    EvidenceReferenceQuery,
    EvidenceReferenceResult,
    EvidenceStructure,
    EvidenceStructureDraft,
    IngestRejectedItem,
    IngestResult,
    MarketSnapshot,
    MarketSnapshotDraft,
    MarketSnapshotPage,
    MarketSnapshotQuery,
    RawItem,
)
from consensusinvest.runtime import InternalCallEnvelope


_FORBIDDEN_FACT_FIELDS = {
    "action",
    "bearish",
    "bullish",
    "buy",
    "hold",
    "investment_action",
    "net_impact",
    "recommendation",
    "sell",
    "suggested_action",
    "trade_signal",
    "trading_signal",
}

_ALLOWED_REFERENCE_ROLES = {
    "agent_argument": {"supports", "counters", "cited", "refuted"},
    "round_summary": {"supports", "counters", "cited", "refuted"},
    "judgment": {"supports", "counters", "cited", "refuted"},
    "judge_tool_call": {"cited"},
    "report_view": {"cited"},
}

_ALLOWED_SNAPSHOT_TYPES = {
    "stock_quote",
    "index_quote",
    "sector_heat",
    "concept_heat",
    "market_warning",
}

_T = TypeVar("_T")


class EvidenceStoreClient(Protocol):
    def ingest_search_result(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
    ) -> IngestResult:
        """Ingest a temporary SearchResultPackage into Evidence Store."""

    def query_evidence(
        self,
        envelope: InternalCallEnvelope,
        query: EvidenceQuery | Mapping[str, Any],
    ) -> EvidencePage:
        ...

    def get_evidence(
        self,
        envelope: InternalCallEnvelope,
        evidence_id: str,
    ) -> EvidenceDetail:
        ...

    def get_raw(self, envelope: InternalCallEnvelope, raw_ref: str) -> RawItem:
        ...

    def save_structure(
        self,
        envelope: InternalCallEnvelope,
        draft: EvidenceStructureDraft | Mapping[str, Any],
    ) -> EvidenceStructure:
        ...

    def save_references(
        self,
        envelope: InternalCallEnvelope,
        batch: EvidenceReferenceBatch | Mapping[str, Any],
    ) -> EvidenceReferenceResult:
        ...

    def query_references(
        self,
        envelope: InternalCallEnvelope,
        query: EvidenceReferenceQuery | Mapping[str, Any],
    ) -> list[EvidenceReference]:
        ...

    def save_market_snapshot(
        self,
        envelope: InternalCallEnvelope,
        snapshot: MarketSnapshotDraft | Mapping[str, Any],
    ) -> MarketSnapshot:
        ...

    def query_market_snapshots(
        self,
        envelope: InternalCallEnvelope,
        query: MarketSnapshotQuery | Mapping[str, Any],
    ) -> MarketSnapshotPage:
        ...

    def get_market_snapshot(
        self,
        envelope: InternalCallEnvelope,
        market_snapshot_id: str,
    ) -> MarketSnapshot:
        ...


class InMemoryEvidenceStoreClient:
    """Contract-complete in-memory Evidence Store for tests and local runtime."""

    def __init__(self) -> None:
        self.received_packages: list[Any] = []
        self.received_envelopes: list[InternalCallEnvelope] = []
        self._raw_items: dict[str, RawItem] = {}
        self._evidence_items: dict[str, EvidenceItem] = {}
        self._evidence_by_raw_ref: dict[str, str] = {}
        self._evidence_entities: dict[str, set[str]] = {}
        self._structures_by_evidence_id: dict[str, list[EvidenceStructure]] = {}
        self._references: list[EvidenceReference] = []
        self._market_snapshots: dict[str, MarketSnapshot] = {}
        self._seen_item_keys: set[str] = set()
        self._seen_content_keys: set[str] = set()
        self._next_raw_id = 1
        self._next_evidence_id = 1
        self._next_structure_id = 1
        self._next_reference_id = 1
        self._next_market_snapshot_id = 1
        self.normalizer = EvidenceNormalizer()

    def ingest_search_result(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
    ) -> IngestResult:
        envelope.validate_for_create()
        self.received_envelopes.append(envelope)
        self.received_packages.append(package)

        accepted_raw_refs: list[str] = []
        created_evidence_ids: list[str] = []
        rejected_items: list[IngestRejectedItem] = []

        normalized = self.normalizer.normalize_search_result(envelope, package)
        rejected_items.extend(normalized.rejected_items)

        for draft in normalized.drafts:
            duplicate_key = self._existing_dedupe_key(draft.dedupe_keys)
            if duplicate_key is not None:
                rejected_items.append(
                    IngestRejectedItem(
                        external_id=draft.external_id,
                        reason="duplicate_request",
                        message="search result item was already ingested",
                        item_key=duplicate_key,
                        code="duplicate_request",
                        retryable=True,
                    )
                )
                continue

            raw_item, evidence_item = self._build_raw_and_evidence_from_draft(
                envelope,
                package,
                draft,
            )
            self._raw_items[raw_item.raw_ref] = raw_item
            self._evidence_items[evidence_item.evidence_id] = evidence_item
            self._evidence_by_raw_ref[raw_item.raw_ref] = evidence_item.evidence_id
            self._index_evidence_entities(evidence_item)
            self._remember_dedupe_keys(draft.dedupe_keys)

            accepted_raw_refs.append(raw_item.raw_ref)
            created_evidence_ids.append(evidence_item.evidence_id)

        if accepted_raw_refs and rejected_items:
            status = "partial_accepted"
        elif accepted_raw_refs:
            status = "accepted"
        else:
            status = "rejected"

        return IngestResult(
            task_id=_clean_key_value(_value(package, "task_id")),
            workflow_run_id=_clean_key_value(getattr(envelope, "workflow_run_id", None)),
            status=status,
            accepted_raw_refs=accepted_raw_refs,
            created_evidence_ids=created_evidence_ids,
            updated_evidence_ids=[],
            rejected_items=rejected_items,
        )

    def query_evidence(
        self,
        envelope: InternalCallEnvelope,
        query: EvidenceQuery | Mapping[str, Any],
    ) -> EvidencePage:
        del envelope
        evidence_query = _coerce_dataclass(EvidenceQuery, query)
        publish_lte = _parse_datetime(evidence_query.publish_time_lte)
        publish_gte = _parse_datetime(evidence_query.publish_time_gte)

        rows = list(self._evidence_items.values())
        allowed_evidence_ids = self._matching_evidence_ids_for_entities(evidence_query.entity_ids)
        rows = [
            item
            for item in rows
            if _matches_optional(item.ticker, evidence_query.ticker)
            and (allowed_evidence_ids is None or item.evidence_id in allowed_evidence_ids)
            and _in_if_requested(item.evidence_type, evidence_query.evidence_types)
            and _in_if_requested(item.source, evidence_query.sources)
            and _in_if_requested(item.source_type, evidence_query.source_types)
            and _source_quality_at_least(item.source_quality, evidence_query.source_quality_min)
            and _datetime_lte(item.publish_time, publish_lte)
            and _datetime_gte(item.publish_time, publish_gte)
            and _matches_workflow_run_id(item, evidence_query.workflow_run_id, self._raw_items)
        ]
        rows.sort(key=_evidence_sort_key, reverse=True)
        total = len(rows)
        limit = max(evidence_query.limit, 0)
        offset = max(evidence_query.offset, 0)
        return EvidencePage(
            items=rows[offset : offset + limit],
            total=total,
            limit=evidence_query.limit,
            offset=evidence_query.offset,
        )

    def get_evidence(
        self,
        envelope: InternalCallEnvelope,
        evidence_id: str,
    ) -> EvidenceDetail:
        del envelope
        evidence = self._evidence_items.get(evidence_id)
        if evidence is None:
            raise KeyError(f"evidence_not_found: {evidence_id}")
        structures = self._structures_by_evidence_id.get(evidence_id, [])
        references = [ref for ref in self._references if ref.evidence_id == evidence_id]
        return EvidenceDetail(
            evidence=evidence,
            structure=structures[-1] if structures else None,
            raw_ref=evidence.raw_ref,
            references=references,
        )

    def get_raw(self, envelope: InternalCallEnvelope, raw_ref: str) -> RawItem:
        del envelope
        raw_item = self._raw_items.get(raw_ref)
        if raw_item is None:
            raise KeyError(f"raw_not_found: {raw_ref}")
        return raw_item

    def save_structure(
        self,
        envelope: InternalCallEnvelope,
        draft: EvidenceStructureDraft | Mapping[str, Any],
    ) -> EvidenceStructure:
        envelope.validate_for_create()
        violation_path = _find_forbidden_key(draft)
        if violation_path is not None:
            raise ValueError(
                f"write_boundary_violation: directional field is not allowed in structure: {violation_path}"
            )
        structure_draft = _coerce_dataclass(EvidenceStructureDraft, draft)
        if structure_draft.evidence_id not in self._evidence_items:
            raise KeyError(f"evidence_not_found: {structure_draft.evidence_id}")

        version = len(self._structures_by_evidence_id.get(structure_draft.evidence_id, [])) + 1
        structure = EvidenceStructure(
            structure_id=self._next_id("struct"),
            evidence_id=structure_draft.evidence_id,
            version=version,
            objective_summary=structure_draft.objective_summary,
            key_facts=list(structure_draft.key_facts),
            claims=list(structure_draft.claims),
            structuring_confidence=structure_draft.structuring_confidence,
            quality_notes=tuple(structure_draft.quality_notes),
            created_by_agent_id=structure_draft.created_by_agent_id,
            created_at=_timestamp_for_create(envelope),
        )
        self._structures_by_evidence_id.setdefault(structure.evidence_id, []).append(structure)
        return structure

    def save_references(
        self,
        envelope: InternalCallEnvelope,
        batch: EvidenceReferenceBatch | Mapping[str, Any],
    ) -> EvidenceReferenceResult:
        envelope.validate_for_create()
        reference_batch = _coerce_dataclass(EvidenceReferenceBatch, batch)
        allowed_roles = _ALLOWED_REFERENCE_ROLES.get(reference_batch.source_type)
        if allowed_roles is None:
            raise ValueError(f"invalid_reference_source_type: {reference_batch.source_type}")

        accepted: list[EvidenceReference] = []
        rejected: list[IngestRejectedItem] = []
        for index, ref_data in enumerate(reference_batch.references):
            data = _to_mapping(ref_data)
            evidence_id = _clean_key_value(data.get("evidence_id"))
            role = _clean_key_value(data.get("reference_role"))
            external_id = evidence_id or f"reference[{index}]"
            if evidence_id not in self._evidence_items:
                rejected.append(
                    _rejected(external_id, "evidence_not_found", "referenced evidence_id does not exist")
                )
                continue
            if role not in allowed_roles:
                rejected.append(
                    _rejected(
                        external_id,
                        "write_boundary_violation",
                        f"{reference_batch.source_type} cannot use reference_role={role}",
                    )
                )
                continue

            reference = EvidenceReference(
                reference_id=self._next_id("eref"),
                source_type=reference_batch.source_type,
                source_id=reference_batch.source_id,
                evidence_id=evidence_id,
                reference_role=role,
                round=_as_int(data.get("round")),
                workflow_run_id=envelope.workflow_run_id,
                created_at=_timestamp_for_create(envelope),
            )
            self._references.append(reference)
            accepted.append(reference)

        return EvidenceReferenceResult(
            source_type=reference_batch.source_type,
            source_id=reference_batch.source_id,
            accepted_references=accepted,
            rejected_references=rejected,
        )

    def query_references(
        self,
        envelope: InternalCallEnvelope,
        query: EvidenceReferenceQuery | Mapping[str, Any],
    ) -> list[EvidenceReference]:
        del envelope
        reference_query = _coerce_dataclass(EvidenceReferenceQuery, query)
        rows = [
            ref
            for ref in self._references
            if _matches_optional(ref.evidence_id, reference_query.evidence_id)
            and _matches_optional(ref.source_type, reference_query.source_type)
            and _matches_optional(ref.source_id, reference_query.source_id)
            and _matches_optional(ref.reference_role, reference_query.reference_role)
            and _matches_optional(ref.workflow_run_id, reference_query.workflow_run_id)
        ]
        limit = max(reference_query.limit, 0)
        offset = max(reference_query.offset, 0)
        return rows[offset : offset + limit]

    def save_market_snapshot(
        self,
        envelope: InternalCallEnvelope,
        snapshot: MarketSnapshotDraft | Mapping[str, Any],
    ) -> MarketSnapshot:
        envelope.validate_for_create()
        draft, snapshot_time, fetched_at = _prepare_market_snapshot_for_save(
            envelope,
            snapshot,
        )

        saved = MarketSnapshot(
            market_snapshot_id=self._next_id("mkt_snap"),
            snapshot_type=draft.snapshot_type,
            ticker=_clean_key_value(draft.ticker),
            entity_ids=tuple(_clean_sequence(draft.entity_ids)),
            source=_clean_key_value(draft.source),
            snapshot_time=snapshot_time,
            fetched_at=fetched_at,
            metrics=dict(draft.metrics),
            ingest_context=_ingest_context(envelope, task_id=None),
        )
        self._market_snapshots[saved.market_snapshot_id] = saved
        return saved

    def query_market_snapshots(
        self,
        envelope: InternalCallEnvelope,
        query: MarketSnapshotQuery | Mapping[str, Any],
    ) -> MarketSnapshotPage:
        snapshot_query = _coerce_dataclass(MarketSnapshotQuery, query)
        snapshot_lte = _parse_datetime(snapshot_query.snapshot_time_lte) or envelope.analysis_time
        snapshot_gte = _parse_datetime(snapshot_query.snapshot_time_gte)
        if snapshot_lte is not None and _datetime_after(snapshot_lte, envelope.analysis_time):
            raise ValueError("snapshot_time_lte cannot be after envelope.analysis_time")

        rows = [
            item
            for item in self._market_snapshots.values()
            if _matches_optional(item.ticker, snapshot_query.ticker)
            and _intersects_if_requested(item.entity_ids, snapshot_query.entity_ids)
            and _in_if_requested(item.snapshot_type, snapshot_query.snapshot_types)
            and _datetime_lte(item.snapshot_time, snapshot_lte)
            and _datetime_gte(item.snapshot_time, snapshot_gte)
        ]
        rows.sort(key=_market_snapshot_sort_key, reverse=True)
        total = len(rows)
        limit = max(snapshot_query.limit, 0)
        offset = max(snapshot_query.offset, 0)
        return MarketSnapshotPage(
            items=rows[offset : offset + limit],
            total=total,
            limit=snapshot_query.limit,
            offset=snapshot_query.offset,
        )

    def get_market_snapshot(
        self,
        envelope: InternalCallEnvelope,
        market_snapshot_id: str,
    ) -> MarketSnapshot:
        del envelope
        snapshot = self._market_snapshots.get(market_snapshot_id)
        if snapshot is None:
            raise KeyError(f"market_snapshot_not_found: {market_snapshot_id}")
        return snapshot

    def _build_raw_and_evidence_from_draft(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
        draft: NormalizedEvidenceDraft,
    ) -> tuple[RawItem, EvidenceItem]:
        raw_ref = self._next_id("raw")
        evidence_id = self._next_id("ev")
        raw_item = RawItem(
            raw_ref=raw_ref,
            source=draft.raw.source,
            source_type=draft.raw.source_type,
            ticker=draft.raw.ticker,
            entity_ids=draft.raw.entity_ids,
            title=draft.raw.title,
            content=draft.raw.content,
            content_preview=draft.raw.content_preview,
            url=draft.raw.url,
            publish_time=draft.raw.publish_time,
            fetched_at=draft.raw.fetched_at,
            author=draft.raw.author,
            language=draft.raw.language,
            raw_payload=dict(draft.raw.raw_payload),
            ingest_context=_ingest_context(
                envelope,
                task_id=_clean_key_value(_value(package, "task_id")),
            ),
        )
        evidence_item = EvidenceItem(
            evidence_id=evidence_id,
            raw_ref=raw_ref,
            ticker=draft.evidence.ticker,
            entity_ids=draft.evidence.entity_ids,
            source=draft.evidence.source,
            source_type=draft.evidence.source_type,
            evidence_type=draft.evidence.evidence_type,
            title=draft.evidence.title,
            content=draft.evidence.content,
            url=draft.evidence.url,
            publish_time=draft.evidence.publish_time,
            fetched_at=draft.evidence.fetched_at,
            source_quality=draft.evidence.source_quality,
            relevance=draft.evidence.relevance,
            freshness=draft.evidence.freshness,
            quality_notes=draft.evidence.quality_notes,
        )
        return raw_item, evidence_item

    def _next_id(self, prefix: str) -> str:
        if prefix == "raw":
            value = self._next_raw_id
            self._next_raw_id += 1
        elif prefix == "ev":
            value = self._next_evidence_id
            self._next_evidence_id += 1
        elif prefix == "struct":
            value = self._next_structure_id
            self._next_structure_id += 1
        elif prefix == "eref":
            value = self._next_reference_id
            self._next_reference_id += 1
        elif prefix == "mkt_snap":
            value = self._next_market_snapshot_id
            self._next_market_snapshot_id += 1
        else:
            raise ValueError(f"unknown id prefix: {prefix}")
        return f"{prefix}_{value:06d}"

    def _existing_dedupe_key(self, item_keys: tuple[str, ...]) -> str | None:
        for key in item_keys:
            if key in self._seen_item_keys or key in self._seen_content_keys:
                return key
        return None

    def _remember_dedupe_keys(self, item_keys: tuple[str, ...]) -> None:
        for key in item_keys:
            if key.startswith("content:"):
                self._seen_content_keys.add(key)
            else:
                self._seen_item_keys.add(key)

    def _index_evidence_entities(self, item: EvidenceItem) -> None:
        for entity_id in item.entity_ids:
            self._evidence_entities.setdefault(entity_id, set()).add(item.evidence_id)

    def _matching_evidence_ids_for_entities(self, entity_ids: Sequence[str]) -> set[str] | None:
        requested = _clean_sequence(entity_ids)
        if not requested:
            return None
        result: set[str] = set()
        for entity_id in requested:
            result.update(self._evidence_entities.get(entity_id, set()))
        return result


class FakeEvidenceStoreClient(InMemoryEvidenceStoreClient):
    """Backward-compatible name used by Search Agent contract tests."""


EvidenceStore = InMemoryEvidenceStoreClient


def _matches_workflow_run_id(
    item: EvidenceItem,
    workflow_run_id: str | None,
    raw_items: Mapping[str, RawItem],
) -> bool:
    if workflow_run_id is None:
        return True
    raw_item = raw_items.get(item.raw_ref)
    if raw_item is None:
        return False
    return raw_item.ingest_context.get("workflow_run_id") == workflow_run_id


def _ingest_context(envelope: InternalCallEnvelope, *, task_id: str | None) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "workflow_run_id": envelope.workflow_run_id,
        "requested_by": envelope.requested_by,
        "correlation_id": envelope.correlation_id,
    }


def _prepare_market_snapshot_for_save(
    envelope: InternalCallEnvelope,
    snapshot: MarketSnapshotDraft | Mapping[str, Any],
) -> tuple[MarketSnapshotDraft, datetime, datetime]:
    violation_path = _find_forbidden_key(snapshot)
    if violation_path is not None:
        raise ValueError(
            f"write_boundary_violation: directional field is not allowed in MarketSnapshot: {violation_path}"
        )
    draft = _coerce_dataclass(MarketSnapshotDraft, snapshot)
    if draft.snapshot_type not in _ALLOWED_SNAPSHOT_TYPES:
        raise ValueError(f"invalid_snapshot_type: {draft.snapshot_type}")
    snapshot_time = _parse_datetime(draft.snapshot_time)
    if snapshot_time is None:
        raise ValueError("snapshot_time is required")
    if _datetime_after(snapshot_time, envelope.analysis_time):
        raise ValueError("snapshot_time cannot be after envelope.analysis_time")
    fetched_at = _parse_datetime(draft.fetched_at) or _timestamp_for_create(envelope)
    return draft, snapshot_time, fetched_at


def _rejected(external_id: str | None, reason: str, message: str) -> IngestRejectedItem:
    return IngestRejectedItem(
        external_id=external_id,
        reason=reason,
        message=message,
        code=reason,
    )


def _coerce_dataclass(cls: type[_T], value: Any) -> _T:
    if isinstance(value, cls):
        return value
    data = _to_mapping(value)
    allowed = {field.name for field in fields(cls)}
    return cls(**{key: data[key] for key in allowed if key in data})


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    result: dict[str, Any] = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(value, name)
        except Exception:
            continue
        if callable(attr):
            continue
        result[name] = attr
    return result


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _find_forbidden_key(value: Any, *, skip_keys: set[str] | None = None, path: str = "") -> str | None:
    skip = skip_keys or set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_norm = key_text.strip().lower()
            child_path = f"{path}.{key_text}" if path else key_text
            if key_norm in skip:
                continue
            if key_norm in _FORBIDDEN_FACT_FIELDS:
                return child_path
            found = _find_forbidden_key(child, skip_keys=skip, path=child_path)
            if found is not None:
                return found
    elif is_dataclass(value) and not isinstance(value, type):
        return _find_forbidden_key(asdict(value), skip_keys=skip, path=path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            found = _find_forbidden_key(child, skip_keys=skip, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


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
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            cleaned = _clean_key_value(item)
            if cleaned is not None and cleaned not in result:
                result.append(cleaned)
        return result
    cleaned = _clean_key_value(value)
    return [cleaned] if cleaned is not None else []


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _timestamp_for_create(envelope: InternalCallEnvelope) -> datetime:
    return envelope.analysis_time or datetime.now(UTC)


def _datetime_after(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return _comparable_datetime(left) > _comparable_datetime(right)


def _datetime_lte(value: datetime | None, boundary: datetime | None) -> bool:
    if boundary is None:
        return True
    if value is None:
        return False
    return _comparable_datetime(value) <= _comparable_datetime(boundary)


def _datetime_gte(value: datetime | None, boundary: datetime | None) -> bool:
    if boundary is None:
        return True
    if value is None:
        return False
    return _comparable_datetime(value) >= _comparable_datetime(boundary)


def _comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _matches_optional(value: Any, expected: Any) -> bool:
    if expected is None:
        return True
    return value == expected


def _intersects_if_requested(values: Sequence[str], requested: Sequence[str]) -> bool:
    if not requested:
        return True
    return bool(set(values) & set(requested))


def _in_if_requested(value: str | None, requested: Sequence[str]) -> bool:
    if not requested:
        return True
    return value in requested


def _source_quality_at_least(value: float | None, minimum: float | None) -> bool:
    if minimum is None:
        return True
    if value is None:
        return False
    return value >= minimum


def _evidence_sort_key(item: EvidenceItem) -> tuple[datetime, str]:
    return (_comparable_datetime(item.publish_time or datetime.min), item.evidence_id)


def _market_snapshot_sort_key(item: MarketSnapshot) -> tuple[datetime, str]:
    return (
        _comparable_datetime(item.snapshot_time or datetime.min),
        item.market_snapshot_id,
    )


__all__ = [
    "EvidenceStore",
    "EvidenceStoreClient",
    "FakeEvidenceStoreClient",
    "InMemoryEvidenceStoreClient",
    "IngestRejectedItem",
    "IngestResult",
]
