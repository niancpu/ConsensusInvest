"""In-memory entity repository for explicit local/test runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EntityRecord:
    entity_id: str
    entity_type: str
    name: str
    aliases: tuple[str, ...] = ()
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True, slots=True)
class EntityRelationRecord:
    relation_id: str
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    weight: float | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


@dataclass(slots=True)
class InMemoryEntityRepository:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    relations: list[EntityRelationRecord] = field(default_factory=list)

    def list_entities(
        self,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[EntityRecord], int]:
        rows = [
            entity
            for entity in self.entities.values()
            if _matches_type(entity, entity_type) and _matches_query(entity, query)
        ]
        rows.sort(key=lambda item: (item.entity_type, item.entity_id))
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_entity(self, entity_id: str) -> EntityRecord | None:
        return self.entities.get(entity_id)

    def upsert_entity(self, record: EntityRecord) -> EntityRecord:
        self.entities[record.entity_id] = record
        return record

    def list_relations(self, entity_id: str, *, depth: int = 1) -> list[EntityRelationRecord]:
        del depth
        return [
            relation
            for relation in self.relations
            if relation.from_entity_id == entity_id or relation.to_entity_id == entity_id
        ]


def seed_entity_repository() -> InMemoryEntityRepository:
    return InMemoryEntityRepository(
        entities={
            "ent_company_002594": EntityRecord(
                entity_id="ent_company_002594",
                entity_type="company",
                name="比亚迪",
                aliases=("BYD", "比亚迪股份", "002594", "002594.SZ"),
                description="A-share listed company.",
            ),
            "ent_company_600519": EntityRecord(
                entity_id="ent_company_600519",
                entity_type="company",
                name="贵州茅台",
                aliases=("Moutai", "茅台", "600519", "600519.SH"),
                description="A-share listed company.",
            ),
            "ent_industry_new_energy_vehicle": EntityRecord(
                entity_id="ent_industry_new_energy_vehicle",
                entity_type="industry",
                name="新能源汽车",
                aliases=("NEV", "新能源车"),
                description="A-share new energy vehicle industry entity.",
            ),
            "ent_concept_low_altitude_economy": EntityRecord(
                entity_id="ent_concept_low_altitude_economy",
                entity_type="concept",
                name="低空经济",
                aliases=("Low Altitude Economy",),
                description="Market concept entity.",
            ),
        },
        relations=[
            EntityRelationRecord(
                relation_id="erel_002594_nev_001",
                from_entity_id="ent_company_002594",
                to_entity_id="ent_industry_new_energy_vehicle",
                relation_type="belongs_to_industry",
                weight=1.0,
                evidence_ids=("ev_000001",),
            ),
            EntityRelationRecord(
                relation_id="erel_nev_002594_001",
                from_entity_id="ent_industry_new_energy_vehicle",
                to_entity_id="ent_company_002594",
                relation_type="has_company",
                weight=1.0,
                evidence_ids=("ev_000001",),
            ),
        ],
    )


def _matches_type(entity: EntityRecord, entity_type: str | None) -> bool:
    return entity_type is None or entity.entity_type == entity_type


def _matches_query(entity: EntityRecord, query: str | None) -> bool:
    if query is None or not query.strip():
        return True
    needle = query.strip().lower()
    values = [entity.entity_id, entity.entity_type, entity.name, *entity.aliases]
    return any(needle in value.lower() for value in values)
