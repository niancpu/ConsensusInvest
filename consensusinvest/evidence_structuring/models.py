"""Evidence Structuring Agent contract models."""

from __future__ import annotations

from dataclasses import dataclass

from consensusinvest.evidence_store.models import EvidenceStructure


@dataclass(frozen=True, slots=True)
class EvidenceStructuringOutcome:
    evidence_id: str
    status: str
    structure: EvidenceStructure | None = None
    reason: str | None = None


__all__ = ["EvidenceStructuringOutcome"]
