"""Stdlib-only SQLite Evidence Store implementation."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from consensusinvest.evidence_normalizer.service import EvidenceNormalizer
from consensusinvest.evidence_normalizer.models import NormalizedEvidenceDraft
from consensusinvest.evidence_store.client import (
    _ALLOWED_REFERENCE_ROLES,
    _as_int,
    _clean_key_value,
    _clean_sequence,
    _coerce_dataclass,
    _datetime_after,
    _datetime_gte,
    _datetime_lte,
    _evidence_sort_key,
    _find_forbidden_key,
    _ingest_context,
    _intersects_if_requested,
    _in_if_requested,
    _market_snapshot_sort_key,
    _matches_optional,
    _matches_workflow_run_id,
    _parse_datetime,
    _prepare_market_snapshot_for_save,
    _rejected,
    _source_quality_at_least,
    _timestamp_for_create,
    _to_mapping,
    _value,
)
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
from consensusinvest.runtime.sqlite import open_sqlite_connection


class SQLiteEvidenceStoreClient:
    """SQLite-backed Evidence Store with the same core contract as the in-memory client."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._sqlite = open_sqlite_connection(self.db_path)
        self._conn = self._sqlite.connection
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.normalizer = EvidenceNormalizer()
        self._ensure_schema()

    def close(self) -> None:
        self._sqlite.close()

    def ingest_search_result(
        self,
        envelope: InternalCallEnvelope,
        package: Any,
    ) -> IngestResult:
        envelope.validate_for_create()
        accepted_raw_refs: list[str] = []
        created_evidence_ids: list[str] = []
        updated_evidence_ids: list[str] = []
        rejected_items: list[IngestRejectedItem] = []

        normalized = self.normalizer.normalize_search_result(envelope, package)
        rejected_items.extend(normalized.rejected_items)

        for draft in normalized.drafts:
            duplicate_key = self._existing_dedupe_key(list(draft.dedupe_keys))
            if duplicate_key is not None:
                existing_evidence_id = self._evidence_id_for_dedupe_key(duplicate_key)
                if self._link_workflow_evidence(envelope.workflow_run_id, existing_evidence_id):
                    updated_evidence_ids.append(existing_evidence_id)
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
            try:
                with self._conn:
                    self._insert_raw(raw_item)
                    self._insert_evidence(evidence_item)
                    self._replace_evidence_entities(evidence_item)
                    self._insert_workflow_evidence_link(
                        envelope.workflow_run_id,
                        evidence_item.evidence_id,
                    )
                    for item_key in draft.dedupe_keys:
                        self._insert_dedupe_key(
                            item_key,
                            raw_item.raw_ref,
                            evidence_item.evidence_id,
                        )
            except sqlite3.IntegrityError:
                rejected_items.append(
                    IngestRejectedItem(
                        external_id=draft.external_id,
                        reason="duplicate_request",
                        message="search result item was already ingested",
                        item_key=draft.dedupe_keys[0] if draft.dedupe_keys else None,
                        code="duplicate_request",
                        retryable=True,
                    )
                )
                continue

            accepted_raw_refs.append(raw_item.raw_ref)
            created_evidence_ids.append(evidence_item.evidence_id)

        if (accepted_raw_refs or updated_evidence_ids) and rejected_items:
            status = "partial_accepted"
        elif accepted_raw_refs or updated_evidence_ids:
            status = "accepted"
        else:
            status = "rejected"

        return IngestResult(
            task_id=_clean_key_value(_value(package, "task_id")),
            workflow_run_id=_clean_key_value(getattr(envelope, "workflow_run_id", None)),
            status=status,
            accepted_raw_refs=accepted_raw_refs,
            created_evidence_ids=created_evidence_ids,
            updated_evidence_ids=updated_evidence_ids,
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
        raw_items = self._load_raw_items_by_ref()
        workflow_links = self._load_workflow_evidence_links(evidence_query.workflow_run_id)
        allowed_evidence_ids = self._matching_evidence_ids_for_entities(
            evidence_query.entity_ids
        )

        rows = [
            item
            for item in self._load_all_evidence()
            if _matches_optional(item.ticker, evidence_query.ticker)
            and (allowed_evidence_ids is None or item.evidence_id in allowed_evidence_ids)
            and _in_if_requested(item.evidence_type, evidence_query.evidence_types)
            and _in_if_requested(item.source, evidence_query.sources)
            and _in_if_requested(item.source_type, evidence_query.source_types)
            and _source_quality_at_least(item.source_quality, evidence_query.source_quality_min)
            and _datetime_lte(item.publish_time, publish_lte)
            and _datetime_gte(item.publish_time, publish_gte)
            and _matches_workflow_run_id(
                item,
                evidence_query.workflow_run_id,
                raw_items,
                workflow_links,
            )
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
        evidence = self._load_evidence(evidence_id)
        if evidence is None:
            raise KeyError(f"evidence_not_found: {evidence_id}")
        structure = self._load_latest_structure(evidence_id)
        references = self.query_references(
            _dummy_envelope(),
            EvidenceReferenceQuery(evidence_id=evidence_id),
        )
        return EvidenceDetail(
            evidence=evidence,
            structure=structure,
            raw_ref=evidence.raw_ref,
            references=references,
        )

    def get_raw(self, envelope: InternalCallEnvelope, raw_ref: str) -> RawItem:
        del envelope
        raw_item = self._load_raw(raw_ref)
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
        if self._load_evidence(structure_draft.evidence_id) is None:
            raise KeyError(f"evidence_not_found: {structure_draft.evidence_id}")

        version = self._next_structure_version(structure_draft.evidence_id)
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
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO evidence_structures (
                    structure_id, evidence_id, version, objective_summary,
                    key_facts_json, claims_json, structuring_confidence,
                    quality_notes_json, created_by_agent_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    structure.structure_id,
                    structure.evidence_id,
                    structure.version,
                    structure.objective_summary,
                    _json_dump(structure.key_facts),
                    _json_dump(list(structure.claims)),
                    structure.structuring_confidence,
                    _json_dump(list(structure.quality_notes)),
                    structure.created_by_agent_id,
                    _dt_dump(structure.created_at),
                ),
            )
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
            if evidence_id is None or self._load_evidence(evidence_id) is None:
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
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO evidence_references (
                        reference_id, source_type, source_id, evidence_id,
                        reference_role, round, workflow_run_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reference.reference_id,
                        reference.source_type,
                        reference.source_id,
                        reference.evidence_id,
                        reference.reference_role,
                        reference.round,
                        reference.workflow_run_id,
                        _dt_dump(reference.created_at),
                    ),
                )
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
            _reference_from_row(row)
            for row in self._conn.execute(
                "SELECT * FROM evidence_references ORDER BY rowid ASC"
            ).fetchall()
        ]
        rows = [
            ref
            for ref in rows
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
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO market_snapshots (
                    market_snapshot_id, snapshot_type, ticker, entity_ids_json,
                    source, snapshot_time, fetched_at, metrics_json, ingest_context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    saved.market_snapshot_id,
                    saved.snapshot_type,
                    saved.ticker,
                    _json_dump(list(saved.entity_ids)),
                    saved.source,
                    _dt_dump(saved.snapshot_time),
                    _dt_dump(saved.fetched_at),
                    _json_dump(saved.metrics),
                    _json_dump(saved.ingest_context),
                ),
            )
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
            for item in self._load_all_market_snapshots()
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
        row = self._conn.execute(
            "SELECT * FROM market_snapshots WHERE market_snapshot_id = ?",
            (market_snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"market_snapshot_not_found: {market_snapshot_id}")
        return _market_snapshot_from_row(row)

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS raw_items (
                    raw_ref TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_type TEXT,
                    ticker TEXT,
                    entity_ids_json TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    content_preview TEXT,
                    url TEXT,
                    publish_time TEXT,
                    fetched_at TEXT,
                    author TEXT,
                    language TEXT,
                    raw_payload_json TEXT NOT NULL,
                    ingest_context_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence_items (
                    evidence_id TEXT PRIMARY KEY,
                    raw_ref TEXT NOT NULL UNIQUE,
                    ticker TEXT,
                    entity_ids_json TEXT NOT NULL,
                    source TEXT,
                    source_type TEXT,
                    evidence_type TEXT,
                    title TEXT,
                    content TEXT,
                    url TEXT,
                    publish_time TEXT,
                    fetched_at TEXT,
                    source_quality REAL,
                    relevance REAL,
                    freshness REAL,
                    quality_notes_json TEXT NOT NULL,
                    FOREIGN KEY(raw_ref) REFERENCES raw_items(raw_ref)
                );

                CREATE TABLE IF NOT EXISTS evidence_entities (
                    evidence_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    PRIMARY KEY(evidence_id, entity_id),
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(evidence_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_entities_entity_id
                    ON evidence_entities(entity_id);

                CREATE TABLE IF NOT EXISTS evidence_structures (
                    structure_id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    objective_summary TEXT NOT NULL,
                    key_facts_json TEXT NOT NULL,
                    claims_json TEXT NOT NULL,
                    structuring_confidence REAL,
                    quality_notes_json TEXT NOT NULL,
                    created_by_agent_id TEXT,
                    created_at TEXT,
                    UNIQUE(evidence_id, version),
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(evidence_id)
                );

                CREATE TABLE IF NOT EXISTS evidence_references (
                    reference_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    reference_role TEXT NOT NULL,
                    round INTEGER,
                    workflow_run_id TEXT,
                    created_at TEXT,
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(evidence_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_evidence_links (
                    workflow_run_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(workflow_run_id, evidence_id),
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(evidence_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_evidence_links_workflow
                    ON workflow_evidence_links(workflow_run_id);

                CREATE TABLE IF NOT EXISTS market_snapshots (
                    market_snapshot_id TEXT PRIMARY KEY,
                    snapshot_type TEXT NOT NULL,
                    ticker TEXT,
                    entity_ids_json TEXT NOT NULL,
                    source TEXT,
                    snapshot_time TEXT,
                    fetched_at TEXT,
                    metrics_json TEXT NOT NULL,
                    ingest_context_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dedupe_keys (
                    item_key TEXT PRIMARY KEY,
                    raw_ref TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(raw_ref) REFERENCES raw_items(raw_ref),
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(evidence_id)
                );
                """
            )

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

    def _insert_raw(self, item: RawItem) -> None:
        self._conn.execute(
            """
            INSERT INTO raw_items (
                raw_ref, source, source_type, ticker, entity_ids_json,
                title, content, content_preview, url, publish_time, fetched_at,
                author, language, raw_payload_json, ingest_context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.raw_ref,
                item.source,
                item.source_type,
                item.ticker,
                _json_dump(list(item.entity_ids)),
                item.title,
                item.content,
                item.content_preview,
                item.url,
                _dt_dump(item.publish_time),
                _dt_dump(item.fetched_at),
                item.author,
                item.language,
                _json_dump(item.raw_payload),
                _json_dump(item.ingest_context),
            ),
        )

    def _insert_evidence(self, item: EvidenceItem) -> None:
        self._conn.execute(
            """
            INSERT INTO evidence_items (
                evidence_id, raw_ref, ticker, entity_ids_json, source, source_type,
                evidence_type, title, content, url, publish_time, fetched_at,
                source_quality, relevance, freshness, quality_notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.evidence_id,
                item.raw_ref,
                item.ticker,
                _json_dump(list(item.entity_ids)),
                item.source,
                item.source_type,
                item.evidence_type,
                item.title,
                item.content,
                item.url,
                _dt_dump(item.publish_time),
                _dt_dump(item.fetched_at),
                item.source_quality,
                item.relevance,
                item.freshness,
                _json_dump(list(item.quality_notes)),
            ),
        )

    def _replace_evidence_entities(self, item: EvidenceItem) -> None:
        self._conn.execute(
            "DELETE FROM evidence_entities WHERE evidence_id = ?",
            (item.evidence_id,),
        )
        for entity_id in _clean_sequence(item.entity_ids):
            self._conn.execute(
                """
                INSERT OR IGNORE INTO evidence_entities (evidence_id, entity_id)
                VALUES (?, ?)
                """,
                (item.evidence_id, entity_id),
            )

    def _insert_dedupe_key(self, item_key: str, raw_ref: str, evidence_id: str) -> None:
        self._conn.execute(
            "INSERT INTO dedupe_keys (item_key, raw_ref, evidence_id) VALUES (?, ?, ?)",
            (item_key, raw_ref, evidence_id),
        )

    def _insert_workflow_evidence_link(
        self,
        workflow_run_id: str | None,
        evidence_id: str | None,
    ) -> bool:
        workflow_id = _clean_key_value(workflow_run_id)
        evidence_key = _clean_key_value(evidence_id)
        if workflow_id is None or evidence_key is None:
            return False
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO workflow_evidence_links (workflow_run_id, evidence_id)
            VALUES (?, ?)
            """,
            (workflow_id, evidence_key),
        )
        return cursor.rowcount > 0

    def _link_workflow_evidence(
        self,
        workflow_run_id: str | None,
        evidence_id: str | None,
    ) -> bool:
        with self._conn:
            return self._insert_workflow_evidence_link(workflow_run_id, evidence_id)

    def _existing_dedupe_key(self, item_keys: list[str]) -> str | None:
        for key in item_keys:
            row = self._conn.execute(
                "SELECT item_key FROM dedupe_keys WHERE item_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                return str(row["item_key"])
        return None

    def _evidence_id_for_dedupe_key(self, item_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT evidence_id FROM dedupe_keys WHERE item_key = ?",
            (item_key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["evidence_id"])

    def _next_id(self, prefix: str) -> str:
        key = f"next_{prefix}_id"
        with self._conn:
            row = self._conn.execute(
                "SELECT value FROM metadata WHERE key = ?",
                (key,),
            ).fetchone()
            current = int(row["value"]) if row is not None else 1
            self._conn.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, current + 1),
            )
        return f"{prefix}_{current:06d}"

    def _next_structure_version(self, evidence_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS max_version FROM evidence_structures WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        return int(row["max_version"]) + 1

    def _load_raw(self, raw_ref: str) -> RawItem | None:
        row = self._conn.execute(
            "SELECT * FROM raw_items WHERE raw_ref = ?",
            (raw_ref,),
        ).fetchone()
        return _raw_from_row(row) if row is not None else None

    def _load_evidence(self, evidence_id: str) -> EvidenceItem | None:
        row = self._conn.execute(
            "SELECT * FROM evidence_items WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        return _evidence_from_row(row) if row is not None else None

    def _load_all_evidence(self) -> list[EvidenceItem]:
        return [
            _evidence_from_row(row)
            for row in self._conn.execute("SELECT * FROM evidence_items").fetchall()
        ]

    def _matching_evidence_ids_for_entities(self, entity_ids: tuple[str, ...]) -> set[str] | None:
        requested = _clean_sequence(entity_ids)
        if not requested:
            return None
        placeholders = ",".join("?" for _ in requested)
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT evidence_id
            FROM evidence_entities
            WHERE entity_id IN ({placeholders})
            """,
            tuple(requested),
        ).fetchall()
        return {str(row["evidence_id"]) for row in rows}

    def _load_raw_items_by_ref(self) -> dict[str, RawItem]:
        return {
            item.raw_ref: item
            for item in (
                _raw_from_row(row)
                for row in self._conn.execute("SELECT * FROM raw_items").fetchall()
            )
        }

    def _load_workflow_evidence_links(
        self,
        workflow_run_id: str | None,
    ) -> dict[str, set[str]] | None:
        workflow_id = _clean_key_value(workflow_run_id)
        if workflow_id is None:
            return None
        rows = self._conn.execute(
            """
            SELECT evidence_id
            FROM workflow_evidence_links
            WHERE workflow_run_id = ?
            """,
            (workflow_id,),
        ).fetchall()
        return {workflow_id: {str(row["evidence_id"]) for row in rows}}

    def _load_latest_structure(self, evidence_id: str) -> EvidenceStructure | None:
        row = self._conn.execute(
            """
            SELECT * FROM evidence_structures
            WHERE evidence_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (evidence_id,),
        ).fetchone()
        return _structure_from_row(row) if row is not None else None

    def _load_all_market_snapshots(self) -> list[MarketSnapshot]:
        return [
            _market_snapshot_from_row(row)
            for row in self._conn.execute("SELECT * FROM market_snapshots").fetchall()
        ]


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _dt_dump(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _raw_from_row(row: sqlite3.Row) -> RawItem:
    return RawItem(
        raw_ref=row["raw_ref"],
        source=row["source"],
        source_type=row["source_type"],
        ticker=row["ticker"],
        entity_ids=tuple(_json_load(row["entity_ids_json"], [])),
        title=row["title"],
        content=row["content"],
        content_preview=row["content_preview"],
        url=row["url"],
        publish_time=_parse_datetime(row["publish_time"]),
        fetched_at=_parse_datetime(row["fetched_at"]),
        author=row["author"],
        language=row["language"],
        raw_payload=dict(_json_load(row["raw_payload_json"], {})),
        ingest_context=dict(_json_load(row["ingest_context_json"], {})),
    )


def _evidence_from_row(row: sqlite3.Row) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=row["evidence_id"],
        raw_ref=row["raw_ref"],
        ticker=row["ticker"],
        entity_ids=tuple(_json_load(row["entity_ids_json"], [])),
        source=row["source"],
        source_type=row["source_type"],
        evidence_type=row["evidence_type"],
        title=row["title"],
        content=row["content"],
        url=row["url"],
        publish_time=_parse_datetime(row["publish_time"]),
        fetched_at=_parse_datetime(row["fetched_at"]),
        source_quality=row["source_quality"],
        relevance=row["relevance"],
        freshness=row["freshness"],
        quality_notes=tuple(_json_load(row["quality_notes_json"], [])),
    )


def _structure_from_row(row: sqlite3.Row) -> EvidenceStructure:
    return EvidenceStructure(
        structure_id=row["structure_id"],
        evidence_id=row["evidence_id"],
        version=row["version"],
        objective_summary=row["objective_summary"],
        key_facts=list(_json_load(row["key_facts_json"], [])),
        claims=list(_json_load(row["claims_json"], [])),
        structuring_confidence=row["structuring_confidence"],
        quality_notes=tuple(_json_load(row["quality_notes_json"], [])),
        created_by_agent_id=row["created_by_agent_id"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _reference_from_row(row: sqlite3.Row) -> EvidenceReference:
    return EvidenceReference(
        reference_id=row["reference_id"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        evidence_id=row["evidence_id"],
        reference_role=row["reference_role"],
        round=row["round"],
        workflow_run_id=row["workflow_run_id"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _market_snapshot_from_row(row: sqlite3.Row) -> MarketSnapshot:
    return MarketSnapshot(
        market_snapshot_id=row["market_snapshot_id"],
        snapshot_type=row["snapshot_type"],
        ticker=row["ticker"],
        entity_ids=tuple(_json_load(row["entity_ids_json"], [])),
        source=row["source"],
        snapshot_time=_parse_datetime(row["snapshot_time"]),
        fetched_at=_parse_datetime(row["fetched_at"]),
        metrics=dict(_json_load(row["metrics_json"], {})),
        ingest_context=dict(_json_load(row["ingest_context_json"], {})),
    )


def _dummy_envelope() -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="sqlite_internal",
        correlation_id="sqlite_internal",
        workflow_run_id=None,
        analysis_time=datetime.min,
        requested_by="sqlite_evidence_store",
    )


__all__ = ["SQLiteEvidenceStoreClient"]
