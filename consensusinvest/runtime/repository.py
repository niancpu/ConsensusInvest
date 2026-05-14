"""SQLite-backed runtime event repository."""

from __future__ import annotations

import gzip
import json
import sqlite3
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from consensusinvest.runtime.models import RuntimeEvent

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class RuntimeEventArchiveResult:
    archived_count: int
    deleted_count: int
    archive_files: tuple[Path, ...] = field(default_factory=tuple)


class SQLiteRuntimeEventRepository:
    """Append-only runtime event log for Agent-class task auditing."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def append_event(self, event: RuntimeEvent) -> RuntimeEvent:
        stored = event if event.event_id else replace(event, event_id=self._next_event_id())
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO runtime_events (
                    event_id, event_type, occurred_at, correlation_id,
                    workflow_run_id, producer, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.event_id,
                    stored.event_type,
                    _dt_dump(stored.occurred_at),
                    stored.correlation_id,
                    stored.workflow_run_id,
                    stored.producer,
                    _json_dump(stored.payload),
                ),
            )
        return stored

    def list_events(
        self,
        *,
        workflow_run_id: str | None = None,
        correlation_id: str | None = None,
        producer: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RuntimeEvent]:
        conditions: list[str] = []
        params: list[Any] = []
        if workflow_run_id is not None:
            conditions.append("workflow_run_id = ?")
            params.append(workflow_run_id)
        if correlation_id is not None:
            conditions.append("correlation_id = ?")
            params.append(correlation_id)
        if producer is not None:
            conditions.append("producer = ?")
            params.append(producer)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._connection.execute(
            f"""
            SELECT * FROM runtime_events
            {where_sql}
            ORDER BY rowid ASC
            LIMIT ? OFFSET ?
            """,
            [*params, max(limit, 0), max(offset, 0)],
        ).fetchall()
        return [_event_from_row(row) for row in rows]

    def archive_events(
        self,
        *,
        cutoff: datetime,
        archive_dir: str | Path,
        delete_archived: bool = True,
        batch_id: str | None = None,
    ) -> RuntimeEventArchiveResult:
        """Archive terminal runtime events before ``cutoff`` to monthly gzip JSONL files."""
        archive_path = Path(archive_dir)
        archive_path.mkdir(parents=True, exist_ok=True)
        batch = batch_id or datetime.now(UTC).strftime("%Y%m%d%H%M%S")

        rows = self._connection.execute(
            "SELECT rowid, * FROM runtime_events ORDER BY occurred_at ASC, rowid ASC"
        ).fetchall()
        candidates = [_archive_row(row) for row in rows if _dt_before(row["occurred_at"], cutoff)]
        terminal_groups = {
            event.group_key
            for event in candidates
            if event.group_key is not None and _is_terminal_event(event.event)
        }
        archivable = [
            event
            for event in candidates
            if event.group_key is not None and event.group_key in terminal_groups
        ]
        if not archivable:
            return RuntimeEventArchiveResult(archived_count=0, deleted_count=0)

        files_by_month: dict[str, list[_ArchiveEventRow]] = {}
        for event in archivable:
            month = event.event.occurred_at.strftime("%Y-%m")
            files_by_month.setdefault(month, []).append(event)

        archive_files: list[Path] = []
        for month, month_events in sorted(files_by_month.items()):
            file_path = archive_path / f"runtime_events_{month}_{batch}.jsonl.gz"
            with gzip.open(file_path, "wt", encoding="utf-8", newline="\n") as archive_file:
                for event in month_events:
                    archive_file.write(_json_dump(_event_to_archive_record(event.event)))
                    archive_file.write("\n")
            archive_files.append(file_path)

        deleted_count = 0
        if delete_archived:
            rowids = [event.rowid for event in archivable]
            with self._connection:
                self._connection.executemany(
                    "DELETE FROM runtime_events WHERE rowid = ?",
                    ((rowid,) for rowid in rowids),
                )
            deleted_count = len(rowids)

        return RuntimeEventArchiveResult(
            archived_count=len(archivable),
            deleted_count=deleted_count,
            archive_files=tuple(archive_files),
        )

    def _ensure_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runtime_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    workflow_run_id TEXT,
                    producer TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runtime_events_workflow_run
                    ON runtime_events(workflow_run_id);
                CREATE INDEX IF NOT EXISTS idx_runtime_events_correlation
                    ON runtime_events(correlation_id);
                CREATE INDEX IF NOT EXISTS idx_runtime_events_producer
                    ON runtime_events(producer);
                """
            )

    def _next_event_id(self) -> str:
        with self._connection:
            row = self._connection.execute(
                "SELECT value FROM metadata WHERE key = ?",
                ("next_runtime_event_id",),
            ).fetchone()
            current = int(row["value"]) if row is not None else 1
            self._connection.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("next_runtime_event_id", current + 1),
            )
        return f"rtevt_{current:06d}"


def _event_from_row(row: sqlite3.Row) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        occurred_at=_dt_load(row["occurred_at"]),
        correlation_id=row["correlation_id"],
        workflow_run_id=row["workflow_run_id"],
        producer=row["producer"],
        payload=dict(_json_load(row["payload_json"], {})),
    )


@dataclass(frozen=True, slots=True)
class _ArchiveEventRow:
    rowid: int
    event: RuntimeEvent
    group_key: str | None


def _archive_row(row: sqlite3.Row) -> _ArchiveEventRow:
    event = _event_from_row(row)
    return _ArchiveEventRow(
        rowid=int(row["rowid"]),
        event=event,
        group_key=_event_group_key(event),
    )


def _event_group_key(event: RuntimeEvent) -> str | None:
    agent_run_id = event.payload.get("agent_run_id")
    if agent_run_id:
        return f"agent_run_id:{agent_run_id}"
    task_id = event.payload.get("task_id")
    if task_id:
        return f"task_id:{task_id}"
    return None


def _is_terminal_event(event: RuntimeEvent) -> bool:
    status = event.payload.get("status")
    if isinstance(status, str) and status in _TERMINAL_STATUSES:
        return True
    return event.event_type in _TERMINAL_STATUSES


def _event_to_archive_record(event: RuntimeEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "occurred_at": _dt_dump(event.occurred_at),
        "correlation_id": event.correlation_id,
        "workflow_run_id": event.workflow_run_id,
        "producer": event.producer,
        "payload": event.payload,
    }


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


def _dt_dump(value: datetime) -> str:
    return value.isoformat()


def _dt_load(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _dt_before(value: str, cutoff: datetime) -> bool:
    event_dt = _dt_load(value)
    if event_dt.tzinfo is not None and cutoff.tzinfo is not None:
        return event_dt.astimezone(UTC) < cutoff.astimezone(UTC)
    if event_dt.tzinfo is None and cutoff.tzinfo is None:
        return event_dt < cutoff
    if event_dt.tzinfo is None:
        return event_dt.replace(tzinfo=UTC) < cutoff.astimezone(UTC)
    return event_dt.astimezone(UTC) < cutoff.replace(tzinfo=UTC)


__all__ = ["RuntimeEventArchiveResult", "SQLiteRuntimeEventRepository"]
