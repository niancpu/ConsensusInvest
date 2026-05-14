"""SQLite persistence for Report Module run records."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ReportRunRecord:
    """Persistent record for one Report Module view build run."""

    report_run_id: str
    ticker: str
    stock_code: str | None
    status: str
    report_mode: str
    data_state: str
    input_refs: dict[str, Any]
    output_snapshot: dict[str, Any]
    limitations: list[str]
    created_at: datetime
    updated_at: datetime
    workflow_run_id: str | None = None
    judgment_id: str | None = None
    entity_id: str | None = None
    refresh_task_id: str | None = None
    error: dict[str, Any] | None = None
    details: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReportViewCacheRecord:
    """Cached Report Module view projection keyed by report view identity."""

    cache_key: str
    report_run_id: str
    report_mode: str
    input_refs: dict[str, Any]
    output_snapshot: dict[str, Any]
    limitations: list[str]
    data_state: str
    created_at: datetime
    updated_at: datetime


class SQLiteReportRunRepository:
    """SQLite-backed Report Module run repository.

    This repository only stores Report Module view run records. It does not
    create Evidence, Judgment, workflow state, or route/service wiring.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteReportRunRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def new_report_run_id(self, ticker: str, created_at: datetime | None = None) -> str:
        created = created_at or datetime.now(timezone.utc)
        normalized_ticker = _normalize_ticker(ticker)
        key = f"rpt:{created.strftime('%Y%m%d')}:{normalized_ticker}"
        value = self._next_sequence(key)
        return f"rpt_{created.strftime('%Y%m%d')}_{normalized_ticker}_{value:04d}"

    def create_run(self, record: ReportRunRecord) -> ReportRunRecord:
        normalized = _normalize_record(record)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO report_runs (
                    report_run_id, ticker, stock_code, workflow_run_id,
                    judgment_id, entity_id, status, report_mode, data_state,
                    input_refs_json, output_snapshot_json, limitations_json,
                    refresh_task_id, error_json, details_json, created_at,
                    updated_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _record_values(normalized),
            )
        return normalized

    def get_run(self, report_run_id: str) -> ReportRunRecord | None:
        row = self._conn.execute(
            "SELECT * FROM report_runs WHERE report_run_id = ?",
            (report_run_id,),
        ).fetchone()
        return _record_from_row(row) if row is not None else None

    def update_run(self, report_run_id: str, **changes: object) -> ReportRunRecord:
        current = self.get_run(report_run_id)
        if current is None:
            raise KeyError(report_run_id)
        allowed = set(ReportRunRecord.__dataclass_fields__) - {"report_run_id"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown report run fields: {', '.join(sorted(unknown))}")
        updated = _normalize_record(replace(current, **changes))
        with self._conn:
            self._conn.execute(
                """
                UPDATE report_runs
                SET ticker = ?,
                    stock_code = ?,
                    workflow_run_id = ?,
                    judgment_id = ?,
                    entity_id = ?,
                    status = ?,
                    report_mode = ?,
                    data_state = ?,
                    input_refs_json = ?,
                    output_snapshot_json = ?,
                    limitations_json = ?,
                    refresh_task_id = ?,
                    error_json = ?,
                    details_json = ?,
                    created_at = ?,
                    updated_at = ?,
                    started_at = ?,
                    completed_at = ?
                WHERE report_run_id = ?
                """,
                (*_record_values(updated)[1:], report_run_id),
            )
        return updated

    def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        stock_code: str | None = None,
        status: str | None = None,
    ) -> list[ReportRunRecord]:
        where: list[str] = []
        params: list[Any] = []
        if stock_code is not None:
            where.append("stock_code = ?")
            params.append(stock_code)
        if status is not None:
            where.append("status = ?")
            params.append(_enum_value(status))
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._conn.execute(
            f"""
            SELECT * FROM report_runs
            {where_sql}
            ORDER BY created_at DESC, report_run_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, max(limit, 0), max(offset, 0)],
        ).fetchall()
        return [_record_from_row(row) for row in rows]

    def count_runs(
        self,
        *,
        stock_code: str | None = None,
        status: str | None = None,
    ) -> int:
        where: list[str] = []
        params: list[Any] = []
        if stock_code is not None:
            where.append("stock_code = ?")
            params.append(stock_code)
        if status is not None:
            where.append("status = ?")
            params.append(_enum_value(status))
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        row = self._conn.execute(
            f"SELECT COUNT(*) AS total FROM report_runs {where_sql}",
            params,
        ).fetchone()
        return int(row["total"]) if row is not None else 0

    def upsert_view_cache(self, record: ReportViewCacheRecord) -> ReportViewCacheRecord:
        normalized = _normalize_cache_record(record)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO report_view_cache (
                    cache_key, report_run_id, report_mode, input_refs_json,
                    output_snapshot_json, limitations_json, data_state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    report_run_id = excluded.report_run_id,
                    report_mode = excluded.report_mode,
                    input_refs_json = excluded.input_refs_json,
                    output_snapshot_json = excluded.output_snapshot_json,
                    limitations_json = excluded.limitations_json,
                    data_state = excluded.data_state,
                    updated_at = excluded.updated_at
                """,
                _cache_values(normalized),
            )
        current = self.get_view_cache(normalized.cache_key)
        if current is None:
            raise KeyError(normalized.cache_key)
        return current

    def get_view_cache(self, cache_key: str) -> ReportViewCacheRecord | None:
        row = self._conn.execute(
            "SELECT * FROM report_view_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        return _cache_from_row(row) if row is not None else None

    def list_view_cache(self, *, limit: int = 20, offset: int = 0) -> list[ReportViewCacheRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM report_view_cache
            ORDER BY updated_at DESC, cache_key DESC
            LIMIT ? OFFSET ?
            """,
            (max(limit, 0), max(offset, 0)),
        ).fetchall()
        return [_cache_from_row(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS id_sequences (
                    sequence_key TEXT PRIMARY KEY,
                    next_value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_runs (
                    report_run_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    stock_code TEXT,
                    workflow_run_id TEXT,
                    judgment_id TEXT,
                    entity_id TEXT,
                    status TEXT NOT NULL,
                    report_mode TEXT NOT NULL,
                    data_state TEXT NOT NULL,
                    input_refs_json TEXT NOT NULL,
                    output_snapshot_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL,
                    refresh_task_id TEXT,
                    error_json TEXT,
                    details_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_report_runs_created_at
                    ON report_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_report_runs_stock_status
                    ON report_runs(stock_code, status);
                CREATE INDEX IF NOT EXISTS idx_report_runs_workflow
                    ON report_runs(workflow_run_id);

                CREATE TABLE IF NOT EXISTS report_view_cache (
                    cache_key TEXT PRIMARY KEY,
                    report_run_id TEXT NOT NULL,
                    report_mode TEXT NOT NULL,
                    input_refs_json TEXT NOT NULL,
                    output_snapshot_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL,
                    data_state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_report_view_cache_report_run
                    ON report_view_cache(report_run_id);
                CREATE INDEX IF NOT EXISTS idx_report_view_cache_updated_at
                    ON report_view_cache(updated_at);
                """
            )
            self._conn.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                ("schema_version", "1"),
            )

    def _next_sequence(self, sequence_key: str) -> int:
        with self._conn:
            row = self._conn.execute(
                "SELECT next_value FROM id_sequences WHERE sequence_key = ?",
                (sequence_key,),
            ).fetchone()
            current = int(row["next_value"]) if row is not None else 1
            self._conn.execute(
                """
                INSERT INTO id_sequences (sequence_key, next_value) VALUES (?, ?)
                ON CONFLICT(sequence_key) DO UPDATE SET next_value = excluded.next_value
                """,
                (sequence_key, current + 1),
            )
        return current


def _record_values(record: ReportRunRecord) -> tuple[Any, ...]:
    return (
        record.report_run_id,
        record.ticker,
        record.stock_code,
        record.workflow_run_id,
        record.judgment_id,
        record.entity_id,
        record.status,
        record.report_mode,
        record.data_state,
        _json_dump(record.input_refs),
        _json_dump(record.output_snapshot),
        _json_dump(record.limitations),
        record.refresh_task_id,
        _json_dump(record.error) if record.error is not None else None,
        _json_dump(record.details) if record.details is not None else None,
        _dt_dump(record.created_at),
        _dt_dump(record.updated_at),
        _dt_dump(record.started_at),
        _dt_dump(record.completed_at),
    )


def _record_from_row(row: sqlite3.Row) -> ReportRunRecord:
    return ReportRunRecord(
        report_run_id=row["report_run_id"],
        ticker=row["ticker"],
        stock_code=row["stock_code"],
        workflow_run_id=row["workflow_run_id"],
        judgment_id=row["judgment_id"],
        entity_id=row["entity_id"],
        status=row["status"],
        report_mode=row["report_mode"],
        data_state=row["data_state"],
        input_refs=dict(_json_load(row["input_refs_json"], {})),
        output_snapshot=dict(_json_load(row["output_snapshot_json"], {})),
        limitations=list(_json_load(row["limitations_json"], [])),
        refresh_task_id=row["refresh_task_id"],
        error=_optional_dict(row["error_json"]),
        details=_optional_dict(row["details_json"]),
        created_at=_dt_load_required(row["created_at"]),
        updated_at=_dt_load_required(row["updated_at"]),
        started_at=_dt_load(row["started_at"]),
        completed_at=_dt_load(row["completed_at"]),
    )


def _cache_values(record: ReportViewCacheRecord) -> tuple[Any, ...]:
    return (
        record.cache_key,
        record.report_run_id,
        record.report_mode,
        _json_dump(record.input_refs),
        _json_dump(record.output_snapshot),
        _json_dump(record.limitations),
        record.data_state,
        _dt_dump(record.created_at),
        _dt_dump(record.updated_at),
    )


def _cache_from_row(row: sqlite3.Row) -> ReportViewCacheRecord:
    return ReportViewCacheRecord(
        cache_key=row["cache_key"],
        report_run_id=row["report_run_id"],
        report_mode=row["report_mode"],
        input_refs=dict(_json_load(row["input_refs_json"], {})),
        output_snapshot=dict(_json_load(row["output_snapshot_json"], {})),
        limitations=list(_json_load(row["limitations_json"], [])),
        data_state=row["data_state"],
        created_at=_dt_load_required(row["created_at"]),
        updated_at=_dt_load_required(row["updated_at"]),
    )


def _normalize_record(record: ReportRunRecord) -> ReportRunRecord:
    return replace(
        record,
        ticker=_normalize_ticker(record.ticker),
        status=_enum_value(record.status),
        report_mode=_enum_value(record.report_mode),
        data_state=_enum_value(record.data_state),
        input_refs=dict(record.input_refs),
        output_snapshot=dict(record.output_snapshot),
        limitations=list(record.limitations),
        error=dict(record.error) if record.error is not None else None,
        details=dict(record.details) if record.details is not None else None,
    )


def _normalize_cache_record(record: ReportViewCacheRecord) -> ReportViewCacheRecord:
    cache_key = record.cache_key.strip()
    if not cache_key:
        raise ValueError("cache_key must not be empty")
    report_run_id = record.report_run_id.strip()
    if not report_run_id:
        raise ValueError("report_run_id must not be empty")
    return replace(
        record,
        cache_key=cache_key,
        report_run_id=report_run_id,
        report_mode=_enum_value(record.report_mode),
        data_state=_enum_value(record.data_state),
        input_refs=dict(record.input_refs),
        output_snapshot=dict(record.output_snapshot),
        limitations=list(record.limitations),
    )


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("ticker must not be empty")
    return normalized


def _enum_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


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
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _optional_dict(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return dict(_json_load(value, {}))


def _dt_dump(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt_load(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _dt_load_required(value: str) -> datetime:
    return datetime.fromisoformat(value)


__all__ = ["ReportRunRecord", "ReportViewCacheRecord", "SQLiteReportRunRepository"]
