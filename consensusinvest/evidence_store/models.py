"""Evidence Store contract models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class IngestRejectedItem:
    external_id: str | None
    reason: str
    message: str
    retryable: bool = False
    item_key: str | None = None
    code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IngestResult:
    task_id: str | None = None
    workflow_run_id: str | None = None
    status: str = "accepted"
    accepted_raw_refs: list[str] = field(default_factory=list)
    created_evidence_ids: list[str] = field(default_factory=list)
    updated_evidence_ids: list[str] = field(default_factory=list)
    rejected_items: list[IngestRejectedItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RawItem:
    raw_ref: str
    source: str
    source_type: str | None
    ticker: str | None
    entity_ids: tuple[str, ...] = ()
    title: str | None = None
    content: str | None = None
    content_preview: str | None = None
    url: str | None = None
    publish_time: datetime | None = None
    fetched_at: datetime | None = None
    author: str | None = None
    language: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    ingest_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    raw_ref: str
    ticker: str | None
    entity_ids: tuple[str, ...] = ()
    source: str | None = None
    source_type: str | None = None
    evidence_type: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    publish_time: datetime | None = None
    fetched_at: datetime | None = None
    source_quality: float | None = None
    relevance: float | None = None
    freshness: float | None = None
    quality_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))
        object.__setattr__(self, "quality_notes", tuple(self.quality_notes))


@dataclass(frozen=True, slots=True)
class EvidenceQuery:
    ticker: str | None = None
    entity_ids: tuple[str, ...] = ()
    workflow_run_id: str | None = None
    evidence_types: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    publish_time_lte: datetime | str | None = None
    publish_time_gte: datetime | str | None = None
    source_quality_min: float | None = None
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))
        object.__setattr__(self, "evidence_types", tuple(self.evidence_types))
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "source_types", tuple(self.source_types))


@dataclass(frozen=True, slots=True)
class EvidencePage:
    items: list[EvidenceItem] = field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class EvidenceStructureDraft:
    evidence_id: str
    objective_summary: str
    key_facts: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    structuring_confidence: float | None = None
    quality_notes: tuple[str, ...] = ()
    created_by_agent_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quality_notes", tuple(self.quality_notes))


@dataclass(frozen=True, slots=True)
class EvidenceStructure:
    structure_id: str
    evidence_id: str
    version: int
    objective_summary: str
    key_facts: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    structuring_confidence: float | None = None
    quality_notes: tuple[str, ...] = ()
    created_by_agent_id: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quality_notes", tuple(self.quality_notes))


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    reference_id: str
    source_type: str
    source_id: str
    evidence_id: str
    reference_role: str
    round: int | None = None
    workflow_run_id: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EvidenceReferenceBatch:
    source_type: str
    source_id: str
    references: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EvidenceReferenceResult:
    source_type: str
    source_id: str
    accepted_references: list[EvidenceReference] = field(default_factory=list)
    rejected_references: list[IngestRejectedItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EvidenceReferenceQuery:
    evidence_id: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    reference_role: str | None = None
    workflow_run_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class EvidenceDetail:
    evidence: EvidenceItem
    structure: EvidenceStructure | None
    raw_ref: str
    references: list[EvidenceReference] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MarketSnapshotDraft:
    snapshot_type: str
    ticker: str | None = None
    entity_ids: tuple[str, ...] = ()
    source: str | None = None
    snapshot_time: datetime | str | None = None
    fetched_at: datetime | str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    market_snapshot_id: str
    snapshot_type: str
    ticker: str | None
    entity_ids: tuple[str, ...] = ()
    source: str | None = None
    snapshot_time: datetime | None = None
    fetched_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    ingest_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))


@dataclass(frozen=True, slots=True)
class MarketSnapshotQuery:
    ticker: str | None = None
    entity_ids: tuple[str, ...] = ()
    snapshot_types: tuple[str, ...] = ()
    snapshot_time_lte: datetime | str | None = None
    snapshot_time_gte: datetime | str | None = None
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))
        object.__setattr__(self, "snapshot_types", tuple(self.snapshot_types))


@dataclass(frozen=True, slots=True)
class MarketSnapshotPage:
    items: list[MarketSnapshot] = field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
