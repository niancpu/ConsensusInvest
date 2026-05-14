"""Deterministic Evidence Structuring Agent."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from consensusinvest.evidence_normalizer.service import find_forbidden_fact_key
from consensusinvest.evidence_store import (
    EvidenceDetail,
    EvidenceStoreClient,
    EvidenceStructureDraft,
    RawItem,
)
from consensusinvest.runtime import InternalCallEnvelope

from .models import EvidenceStructuringOutcome


@dataclass(slots=True)
class EvidenceStructuringAgent:
    evidence_store: EvidenceStoreClient
    agent_id: str = "evidence_structurer_v1"

    def structure_evidence(
        self,
        envelope: InternalCallEnvelope,
        evidence_id: str,
        *,
        force: bool = False,
    ) -> EvidenceStructuringOutcome:
        envelope.validate_for_create()
        detail = self.evidence_store.get_evidence(envelope, evidence_id)
        if detail.structure is not None and not force:
            return EvidenceStructuringOutcome(
                evidence_id=evidence_id,
                status="skipped",
                structure=detail.structure,
                reason="structure_already_exists",
            )

        raw = self.evidence_store.get_raw(envelope, detail.raw_ref)
        draft = self.build_structure_draft(detail, raw)
        structure = self.evidence_store.save_structure(envelope, draft)
        return EvidenceStructuringOutcome(
            evidence_id=evidence_id,
            status="structured",
            structure=structure,
        )

    def structure_many(
        self,
        envelope: InternalCallEnvelope,
        evidence_ids: Iterable[str],
        *,
        force: bool = False,
    ) -> list[EvidenceStructuringOutcome]:
        return [
            self.structure_evidence(envelope, evidence_id, force=force)
            for evidence_id in evidence_ids
        ]

    def build_structure_draft(
        self,
        detail: EvidenceDetail,
        raw: RawItem | None = None,
    ) -> EvidenceStructureDraft:
        evidence = detail.evidence
        source_text = _first_text(
            evidence.content,
            evidence.title,
            raw.content if raw is not None else None,
            raw.content_preview if raw is not None else None,
            raw.title if raw is not None else None,
        )
        objective_summary = _summary(source_text)
        claim_span = _span(source_text)
        claims = []
        if claim_span:
            claims.append(
                {
                    "claim": objective_summary,
                    "evidence_span": claim_span,
                    "claim_type": "reported_fact",
                }
            )

        key_facts = []
        if evidence.publish_time is not None:
            key_facts.append(
                {
                    "name": "publish_time",
                    "value": evidence.publish_time.isoformat(),
                    "unit": None,
                    "period": None,
                }
            )
        if evidence.source is not None:
            key_facts.append(
                {
                    "name": "source",
                    "value": evidence.source,
                    "unit": None,
                    "period": None,
                }
            )

        quality_notes = _quality_notes(detail, raw, bool(claims))
        draft = EvidenceStructureDraft(
            evidence_id=evidence.evidence_id,
            objective_summary=objective_summary,
            key_facts=key_facts,
            claims=claims,
            structuring_confidence=_structuring_confidence(source_text, detail),
            quality_notes=quality_notes,
            created_by_agent_id=self.agent_id,
        )
        violation_path = find_forbidden_fact_key(draft)
        if violation_path is not None:
            raise ValueError(
                f"write_boundary_violation: directional field is not allowed in structure: {violation_path}"
            )
        return draft


def _first_text(*values: str | None) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return "No objective source text available."


def _summary(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= 180:
        return cleaned
    return cleaned[:177].rstrip() + "..."


def _span(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    return cleaned[:240]


def _quality_notes(
    detail: EvidenceDetail,
    raw: RawItem | None,
    has_claim: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    for note in detail.evidence.quality_notes:
        if note not in notes:
            notes.append(note)
    if raw is not None and not raw.content and raw.content_preview:
        notes.append("structured_from_preview")
    if not has_claim:
        notes.append("no_claim_extracted")
    return tuple(notes)


def _structuring_confidence(text: str, detail: EvidenceDetail) -> float:
    base = 0.72 if len(text.strip()) >= 20 else 0.58
    if detail.evidence.source_quality is not None:
        base = (base + detail.evidence.source_quality) / 2
    if detail.evidence.relevance is not None:
        base = (base + detail.evidence.relevance) / 2
    return round(max(0.0, min(1.0, base)), 2)


__all__ = ["EvidenceStructuringAgent", "EvidenceStructuringOutcome"]
