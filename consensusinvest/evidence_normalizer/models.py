"""Evidence Normalizer contract models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from consensusinvest.evidence_store.models import EvidenceItem, IngestRejectedItem, RawItem


@dataclass(frozen=True, slots=True)
class RawItemDraft:
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))


@dataclass(frozen=True, slots=True)
class EvidenceItemDraft:
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
class NormalizedEvidenceDraft:
    raw: RawItemDraft
    evidence: EvidenceItemDraft
    external_id: str | None
    dedupe_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dedupe_keys", tuple(self.dedupe_keys))


@dataclass(frozen=True, slots=True)
class EvidenceNormalizationResult:
    drafts: list[NormalizedEvidenceDraft] = field(default_factory=list)
    rejected_items: list["IngestRejectedItem"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NormalizedSearchResult:
    status: str
    raw_items: list["RawItem"] = field(default_factory=list)
    evidence_items: list["EvidenceItem"] = field(default_factory=list)
    rejected_items: list["IngestRejectedItem"] = field(default_factory=list)


__all__ = [
    "EvidenceItemDraft",
    "EvidenceNormalizationResult",
    "NormalizedEvidenceDraft",
    "NormalizedSearchResult",
    "RawItemDraft",
]
