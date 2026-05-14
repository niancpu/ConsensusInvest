from __future__ import annotations

from pathlib import Path

from consensusinvest.entities import EntityRecord, EntityRelationRecord, SQLiteEntityRepository


def _seed(repo: SQLiteEntityRepository) -> None:
    repo.upsert_entity(
        EntityRecord(
            entity_id="ent_company_002594",
            entity_type="company",
            name="比亚迪",
            aliases=("BYD", "比亚迪股份", "002594", "002594.SZ"),
            description="A-share listed company.",
        )
    )
    repo.upsert_entity(
        EntityRecord(
            entity_id="ent_company_600519",
            entity_type="company",
            name="贵州茅台",
            aliases=("Moutai", "茅台", "600519", "600519.SH"),
            description="A-share listed company.",
        )
    )
    repo.upsert_entity(
        EntityRecord(
            entity_id="ent_industry_new_energy_vehicle",
            entity_type="industry",
            name="新能源汽车",
            aliases=("NEV", "新能源车"),
            description="A-share new energy vehicle industry entity.",
        )
    )
    repo.upsert_entity(
        EntityRecord(
            entity_id="ent_concept_low_altitude_economy",
            entity_type="concept",
            name="低空经济",
            aliases=("Low Altitude Economy",),
            description="Market concept entity.",
        )
    )
    repo.upsert_relation(
        EntityRelationRecord(
            relation_id="erel_002594_nev_001",
            from_entity_id="ent_company_002594",
            to_entity_id="ent_industry_new_energy_vehicle",
            relation_type="belongs_to_industry",
            weight=1.0,
            evidence_ids=("ev_000001",),
        )
    )
    repo.upsert_relation(
        EntityRelationRecord(
            relation_id="erel_nev_002594_001",
            from_entity_id="ent_industry_new_energy_vehicle",
            to_entity_id="ent_company_002594",
            relation_type="has_company",
            weight=1.0,
            evidence_ids=("ev_000001",),
        )
    )


def test_sqlite_entity_repository_saves_and_queries_entities(tmp_path: Path) -> None:
    repo = SQLiteEntityRepository(tmp_path / "entities.sqlite3")
    _seed(repo)

    entity = repo.get_entity("ent_company_002594")
    assert entity == EntityRecord(
        entity_id="ent_company_002594",
        entity_type="company",
        name="比亚迪",
        aliases=("BYD", "比亚迪股份", "002594", "002594.SZ"),
        description="A-share listed company.",
    )

    rows, total = repo.list_entities(query="BYD", entity_type="company", limit=20, offset=0)
    assert total == 1
    assert [row.entity_id for row in rows] == ["ent_company_002594"]

    rows, total = repo.list_entities(entity_type="company", limit=20, offset=0)
    assert total == 2
    assert [row.entity_id for row in rows] == ["ent_company_002594", "ent_company_600519"]

    rows, total = repo.list_entities(limit=2, offset=1)
    assert total == 4
    assert [row.entity_id for row in rows] == [
        "ent_company_600519",
        "ent_concept_low_altitude_economy",
    ]

    repo.close()


def test_sqlite_entity_repository_lists_relations_and_reopens(tmp_path: Path) -> None:
    db_path = tmp_path / "entities.sqlite3"
    repo = SQLiteEntityRepository(db_path)
    _seed(repo)

    relations = repo.list_relations("ent_company_002594", depth=1)
    assert [relation.relation_id for relation in relations] == [
        "erel_002594_nev_001",
        "erel_nev_002594_001",
    ]
    assert relations[0].evidence_ids == ("ev_000001",)
    repo.close()

    reopened = SQLiteEntityRepository(db_path)
    try:
        assert reopened.get_entity("ent_company_002594") is not None
        restored_relations = reopened.list_relations("ent_company_002594", depth=1)
        assert [relation.relation_id for relation in restored_relations] == [
            "erel_002594_nev_001",
            "erel_nev_002594_001",
        ]

        reopened.clear()
        rows, total = reopened.list_entities(limit=20, offset=0)
        assert rows == []
        assert total == 0
        assert reopened.list_relations("ent_company_002594") == []
    finally:
        reopened.close()
