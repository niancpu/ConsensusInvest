"""SQLite-backed entity repository."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from consensusinvest.entities.repository import EntityRecord, EntityRelationRecord, _matches_query, _matches_type


class SQLiteEntityRepository:
    """Persistent repository for entities and entity relations.

    This repository owns only the Entity layer projection. It does not write
    Evidence Store tables or cross-table evidence/entity mappings.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteEntityRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

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
            for entity in self._load_entities()
            if _matches_type(entity, entity_type) and _matches_query(entity, query)
        ]
        rows.sort(key=lambda item: (item.entity_type, item.entity_id))
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_entity(self, entity_id: str) -> EntityRecord | None:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        return _entity_from_row(row) if row is not None else None

    def list_relations(self, entity_id: str, *, depth: int = 1) -> list[EntityRelationRecord]:
        del depth
        rows = self._conn.execute(
            """
            SELECT * FROM entity_relations
            WHERE from_entity_id = ? OR to_entity_id = ?
            ORDER BY relation_order ASC, relation_id ASC
            """,
            (entity_id, entity_id),
        ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def upsert_entity(self, record: EntityRecord) -> EntityRecord:
        normalized = EntityRecord(
            entity_id=record.entity_id,
            entity_type=record.entity_type,
            name=record.name,
            aliases=tuple(record.aliases),
            description=record.description,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO entities (
                    entity_id, entity_type, name, aliases_json, description
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    name = excluded.name,
                    aliases_json = excluded.aliases_json,
                    description = excluded.description
                """,
                (
                    normalized.entity_id,
                    normalized.entity_type,
                    normalized.name,
                    _json_dump(list(normalized.aliases)),
                    normalized.description,
                ),
            )
        return normalized

    def upsert_relation(self, record: EntityRelationRecord) -> EntityRelationRecord:
        normalized = EntityRelationRecord(
            relation_id=record.relation_id,
            from_entity_id=record.from_entity_id,
            to_entity_id=record.to_entity_id,
            relation_type=record.relation_type,
            weight=record.weight,
            evidence_ids=tuple(record.evidence_ids),
        )
        with self._conn:
            row = self._conn.execute(
                "SELECT relation_order FROM entity_relations WHERE relation_id = ?",
                (normalized.relation_id,),
            ).fetchone()
            relation_order = int(row["relation_order"]) if row is not None else self._next_relation_order()
            self._conn.execute(
                """
                INSERT INTO entity_relations (
                    relation_id, from_entity_id, to_entity_id, relation_type,
                    weight, evidence_ids_json, relation_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relation_id) DO UPDATE SET
                    from_entity_id = excluded.from_entity_id,
                    to_entity_id = excluded.to_entity_id,
                    relation_type = excluded.relation_type,
                    weight = excluded.weight,
                    evidence_ids_json = excluded.evidence_ids_json,
                    relation_order = excluded.relation_order
                """,
                (
                    normalized.relation_id,
                    normalized.from_entity_id,
                    normalized.to_entity_id,
                    normalized.relation_type,
                    normalized.weight,
                    _json_dump(list(normalized.evidence_ids)),
                    relation_order,
                ),
            )
        return normalized

    def clear(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM entity_relations")
            self._conn.execute("DELETE FROM entities")

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    description TEXT
                );

                CREATE TABLE IF NOT EXISTS entity_relations (
                    relation_id TEXT PRIMARY KEY,
                    from_entity_id TEXT NOT NULL,
                    to_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL,
                    evidence_ids_json TEXT NOT NULL,
                    relation_order INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_entities_type_id
                    ON entities(entity_type, entity_id);
                CREATE INDEX IF NOT EXISTS idx_entity_relations_from
                    ON entity_relations(from_entity_id);
                CREATE INDEX IF NOT EXISTS idx_entity_relations_to
                    ON entity_relations(to_entity_id);
                """
            )
            self._conn.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                ("entity_schema_version", "1"),
            )

    def _load_entities(self) -> list[EntityRecord]:
        rows = self._conn.execute("SELECT * FROM entities").fetchall()
        return [_entity_from_row(row) for row in rows]

    def _next_relation_order(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(relation_order), 0) + 1 AS next_order FROM entity_relations",
        ).fetchone()
        return int(row["next_order"]) if row is not None else 1


def _entity_from_row(row: sqlite3.Row) -> EntityRecord:
    return EntityRecord(
        entity_id=row["entity_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        aliases=tuple(_json_load(row["aliases_json"], [])),
        description=row["description"],
    )


def _relation_from_row(row: sqlite3.Row) -> EntityRelationRecord:
    return EntityRelationRecord(
        relation_id=row["relation_id"],
        from_entity_id=row["from_entity_id"],
        to_entity_id=row["to_entity_id"],
        relation_type=row["relation_type"],
        weight=row["weight"],
        evidence_ids=tuple(_json_load(row["evidence_ids_json"], [])),
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


__all__ = ["SQLiteEntityRepository"]
