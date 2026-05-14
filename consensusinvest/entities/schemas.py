"""Pydantic schemas for Entity Web API projection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from consensusinvest.evidence_store.schemas import EvidenceListItemView


class EntityApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityView(EntityApiModel):
    entity_id: str
    entity_type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None


class EntityRelationView(EntityApiModel):
    relation_id: str
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    weight: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class EntityEvidenceListItemView(EvidenceListItemView):
    pass
