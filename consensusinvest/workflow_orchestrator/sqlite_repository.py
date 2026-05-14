"""SQLite-backed Workflow repository."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from consensusinvest.agent_swarm.models import EvidenceGap, SuggestedSearch

from .models import (
    WorkflowEventRecord,
    WorkflowOptions,
    WorkflowProgress,
    WorkflowQuery,
    WorkflowRunRecord,
)


class SQLiteWorkflowRepository:
    """SQLite Workflow run/event repository with the in-memory repository contract."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteWorkflowRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def create_run(self, run: WorkflowRunRecord) -> WorkflowRunRecord:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO workflow_runs (
                    workflow_run_id, correlation_id, ticker, analysis_time,
                    workflow_config_id, status, stage, query_json, options_json,
                    entity_id, stock_code, created_at, started_at, completed_at,
                    judgment_id, final_signal, confidence, progress_json,
                    failure_code, failure_message, evidence_gaps_json,
                    search_task_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _run_values(run),
            )
            self._conn.execute(
                """
                INSERT INTO workflow_event_sequences (workflow_run_id, next_sequence)
                VALUES (?, 1)
                ON CONFLICT(workflow_run_id) DO NOTHING
                """,
                (run.workflow_run_id,),
            )
        return run

    def new_workflow_run_id(self, *, ticker: str, analysis_time: datetime) -> str:
        value = self._next_id_value("next_workflow_run_id")
        return f"wr_{analysis_time.strftime('%Y%m%d')}_{ticker}_{value:06d}"

    def get_run(self, workflow_run_id: str) -> WorkflowRunRecord | None:
        row = self._conn.execute(
            "SELECT * FROM workflow_runs WHERE workflow_run_id = ?",
            (workflow_run_id,),
        ).fetchone()
        return _run_from_row(row) if row is not None else None

    def update_run(self, workflow_run_id: str, **changes: object) -> WorkflowRunRecord:
        current = self.get_run(workflow_run_id)
        if current is None:
            raise KeyError(workflow_run_id)
        updated = replace(current, **changes)
        with self._conn:
            self._conn.execute(
                """
                UPDATE workflow_runs
                SET correlation_id = ?,
                    ticker = ?,
                    analysis_time = ?,
                    workflow_config_id = ?,
                    status = ?,
                    stage = ?,
                    query_json = ?,
                    options_json = ?,
                    entity_id = ?,
                    stock_code = ?,
                    created_at = ?,
                    started_at = ?,
                    completed_at = ?,
                    judgment_id = ?,
                    final_signal = ?,
                    confidence = ?,
                    progress_json = ?,
                    failure_code = ?,
                    failure_message = ?,
                    evidence_gaps_json = ?,
                    search_task_ids_json = ?
                WHERE workflow_run_id = ?
                """,
                (*_run_values(updated)[1:], workflow_run_id),
            )
        return updated

    def list_runs(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WorkflowRunRecord], int]:
        where: list[str] = []
        params: list[Any] = []
        if ticker is not None:
            where.append("ticker = ?")
            params.append(ticker)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        total_row = self._conn.execute(
            f"SELECT COUNT(*) AS total FROM workflow_runs {where_sql}",
            params,
        ).fetchone()
        total = int(total_row["total"]) if total_row is not None else 0
        rows = self._conn.execute(
            f"""
            SELECT * FROM workflow_runs
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, max(limit, 0), max(offset, 0)],
        ).fetchall()
        return [_run_from_row(row) for row in rows], total

    def append_event(
        self,
        workflow_run_id: str,
        event_type: str,
        payload: dict | None = None,
        *,
        created_at: datetime | None = None,
    ) -> WorkflowEventRecord:
        with self._conn:
            sequence = self._next_event_sequence(workflow_run_id)
            event = WorkflowEventRecord(
                event_id=f"evt_{workflow_run_id}_{sequence:06d}",
                workflow_run_id=workflow_run_id,
                sequence=sequence,
                event_type=event_type,
                created_at=created_at or datetime.now(UTC),
                payload=dict(payload or {}),
            )
            self._conn.execute(
                """
                INSERT INTO workflow_events (
                    event_id, workflow_run_id, sequence, event_type, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.workflow_run_id,
                    event.sequence,
                    event.event_type,
                    _dt_dump(event.created_at),
                    _json_dump(event.payload),
                ),
            )
        return event

    def list_events(
        self,
        workflow_run_id: str,
        *,
        after_sequence: int | None = None,
    ) -> list[WorkflowEventRecord]:
        if after_sequence is None:
            rows = self._conn.execute(
                """
                SELECT * FROM workflow_events
                WHERE workflow_run_id = ?
                ORDER BY sequence ASC
                """,
                (workflow_run_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM workflow_events
                WHERE workflow_run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (workflow_run_id, after_sequence),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def last_event_sequence(self, workflow_run_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) AS sequence
            FROM workflow_events
            WHERE workflow_run_id = ?
            """,
            (workflow_run_id,),
        ).fetchone()
        return int(row["sequence"]) if row is not None else 0

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    workflow_run_id TEXT PRIMARY KEY,
                    correlation_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    analysis_time TEXT NOT NULL,
                    workflow_config_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    entity_id TEXT,
                    stock_code TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    judgment_id TEXT,
                    final_signal TEXT,
                    confidence REAL,
                    progress_json TEXT NOT NULL,
                    failure_code TEXT,
                    failure_message TEXT,
                    evidence_gaps_json TEXT NOT NULL,
                    search_task_ids_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_runs_created_at
                    ON workflow_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_ticker_status
                    ON workflow_runs(ticker, status);

                CREATE TABLE IF NOT EXISTS workflow_event_sequences (
                    workflow_run_id TEXT PRIMARY KEY,
                    next_sequence INTEGER NOT NULL,
                    FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(workflow_run_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_events (
                    event_id TEXT PRIMARY KEY,
                    workflow_run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(workflow_run_id, sequence),
                    FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(workflow_run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_events_run_sequence
                    ON workflow_events(workflow_run_id, sequence);
                """
            )

    def _next_id_value(self, key: str) -> int:
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
        return current

    def _next_event_sequence(self, workflow_run_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT next_sequence FROM workflow_event_sequences
            WHERE workflow_run_id = ?
            """,
            (workflow_run_id,),
        ).fetchone()
        if row is None:
            max_row = self._conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                FROM workflow_events
                WHERE workflow_run_id = ?
                """,
                (workflow_run_id,),
            ).fetchone()
            sequence = int(max_row["next_sequence"]) if max_row is not None else 1
            self._conn.execute(
                """
                INSERT INTO workflow_event_sequences (workflow_run_id, next_sequence)
                VALUES (?, ?)
                """,
                (workflow_run_id, sequence + 1),
            )
            return sequence
        sequence = int(row["next_sequence"])
        self._conn.execute(
            """
            UPDATE workflow_event_sequences
            SET next_sequence = ?
            WHERE workflow_run_id = ?
            """,
            (sequence + 1, workflow_run_id),
        )
        return sequence


def _run_values(run: WorkflowRunRecord) -> tuple[Any, ...]:
    return (
        run.workflow_run_id,
        run.correlation_id,
        run.ticker,
        _dt_dump(run.analysis_time),
        run.workflow_config_id,
        run.status,
        run.stage,
        _json_dump(asdict(run.query)),
        _json_dump(asdict(run.options)),
        run.entity_id,
        run.stock_code,
        _dt_dump(run.created_at),
        _dt_dump(run.started_at),
        _dt_dump(run.completed_at),
        run.judgment_id,
        run.final_signal,
        run.confidence,
        _json_dump(asdict(run.progress)),
        run.failure_code,
        run.failure_message,
        _json_dump([_to_plain(gap) for gap in run.evidence_gaps]),
        _json_dump(list(run.search_task_ids)),
    )


def _run_from_row(row: sqlite3.Row) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        workflow_run_id=row["workflow_run_id"],
        correlation_id=row["correlation_id"],
        ticker=row["ticker"],
        analysis_time=_dt_load(row["analysis_time"]),
        workflow_config_id=row["workflow_config_id"],
        status=row["status"],
        stage=row["stage"],
        query=WorkflowQuery(**_json_load(row["query_json"], {})),
        options=WorkflowOptions(**_json_load(row["options_json"], {})),
        entity_id=row["entity_id"],
        stock_code=row["stock_code"],
        created_at=_dt_load(row["created_at"]),
        started_at=_dt_load_optional(row["started_at"]),
        completed_at=_dt_load_optional(row["completed_at"]),
        judgment_id=row["judgment_id"],
        final_signal=row["final_signal"],
        confidence=row["confidence"],
        progress=WorkflowProgress(**_json_load(row["progress_json"], {})),
        failure_code=row["failure_code"],
        failure_message=row["failure_message"],
        evidence_gaps=tuple(
            _evidence_gap_from_dict(item)
            for item in _json_load(row["evidence_gaps_json"], [])
        ),
        search_task_ids=tuple(_json_load(row["search_task_ids_json"], [])),
    )


def _event_from_row(row: sqlite3.Row) -> WorkflowEventRecord:
    return WorkflowEventRecord(
        event_id=row["event_id"],
        workflow_run_id=row["workflow_run_id"],
        sequence=row["sequence"],
        event_type=row["event_type"],
        created_at=_dt_load(row["created_at"]),
        payload=dict(_json_load(row["payload_json"], {})),
    )


def _evidence_gap_from_dict(data: dict[str, Any]) -> EvidenceGap:
    suggested = data.get("suggested_search")
    return EvidenceGap(
        gap_type=data["gap_type"],
        description=data["description"],
        suggested_search=SuggestedSearch(**suggested) if suggested is not None else None,
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _json_load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _to_plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_plain(asdict(value))
    if isinstance(value, dict):
        return {key: _to_plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(child) for child in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _dt_dump(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt_load(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _dt_load_optional(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


__all__ = ["SQLiteWorkflowRepository"]
