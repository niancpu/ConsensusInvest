"""Pydantic schemas for Evidence Web API projection."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RawItemListView(EvidenceApiModel):
    raw_ref: str
    workflow_run_id: str | None = None
    source: str
    source_type: str | None = None
    ticker: str | None = None
    title: str | None = None
    publish_time: str | None = None
    fetched_at: str | None = None
    url: str | None = None
    payload_preview: dict[str, Any] = Field(default_factory=dict)


class RawItemDetailView(EvidenceApiModel):
    raw_ref: str
    workflow_run_id: str | None = None
    source: str
    source_type: str | None = None
    ticker: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    publish_time: str | None = None
    fetched_at: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    derived_evidence_ids: list[str] = Field(default_factory=list)


class EvidenceListItemView(EvidenceApiModel):
    evidence_id: str
    workflow_run_id: str | None = None
    ticker: str | None = None
    source: str | None = None
    source_type: str | None = None
    evidence_type: str | None = None
    title: str | None = None
    objective_summary: str | None = None
    publish_time: str | None = None
    fetched_at: str | None = None
    source_quality: float | None = None
    relevance: float | None = None
    freshness: float | None = None
    structuring_confidence: float | None = None
    quality_notes: list[str] = Field(default_factory=list)
    raw_ref: str


class EvidenceLinksView(EvidenceApiModel):
    structure: str
    raw: str
    references: str


class EvidenceDetailView(EvidenceApiModel):
    evidence_id: str
    workflow_run_id: str | None = None
    ticker: str | None = None
    source: str | None = None
    source_type: str | None = None
    evidence_type: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    publish_time: str | None = None
    fetched_at: str | None = None
    entities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    objective_summary: str | None = None
    key_facts: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    source_quality: float | None = None
    relevance: float | None = None
    freshness: float | None = None
    structuring_confidence: float | None = None
    quality_notes: list[str] = Field(default_factory=list)
    raw_ref: str
    links: EvidenceLinksView


class EvidenceStructureView(EvidenceApiModel):
    evidence_structure_id: str
    evidence_id: str
    objective_summary: str
    key_facts: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    source_quality: float | None = None
    relevance: float | None = None
    freshness: float | None = None
    structuring_confidence: float | None = None
    quality_notes: list[str] = Field(default_factory=list)
    created_by_agent_id: str | None = None
    created_at: str | None = None


class EvidenceReferenceView(EvidenceApiModel):
    reference_id: str
    workflow_run_id: str | None = None
    source_type: str
    source_id: str
    evidence_id: str
    reference_role: str
    round: int | None = None
    created_at: str | None = None
