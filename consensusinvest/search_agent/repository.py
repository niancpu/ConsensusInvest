from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    SearchTask,
    SearchTaskStatus,
    SourceStatus,
    dataclass_to_dict,
)


class SQLiteSearchTaskRepository:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteSearchTaskRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def create_task(self, task: SearchTask) -> tuple[str, SearchTaskStatus]:
        if task.idempotency_key:
            existing = self.find_by_idempotency_key(task.idempotency_key)
            if existing is not None:
                return existing

        task_id = str(uuid.uuid4())
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO search_tasks (
                    task_id, idempotency_key, status, task_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task.idempotency_key,
                    SearchTaskStatus.QUEUED.value,
                    _to_json(task),
                    now,
                    now,
                ),
            )
            for source in task.scope.sources:
                self.upsert_source_status(
                    task_id,
                    source,
                    SourceStatus.QUEUED,
                    commit=False,
                )
            self.append_event(
                task_id,
                "search.task_queued",
                {
                    "task_id": task_id,
                    "target": dataclass_to_dict(task.target),
                    "sources": list(task.scope.sources),
                },
                commit=False,
            )
        return task_id, SearchTaskStatus.QUEUED

    def find_by_idempotency_key(self, idempotency_key: str) -> tuple[str, SearchTaskStatus] | None:
        row = self._connection.execute(
            "SELECT task_id, status FROM search_tasks WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return row["task_id"], SearchTaskStatus(row["status"])

    def get_task(self, task_id: str) -> SearchTask | None:
        row = self._connection.execute(
            "SELECT task_json FROM search_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return _task_from_json(row["task_json"])

    def update_task_status(self, task_id: str, status: SearchTaskStatus) -> None:
        with self._connection:
            now = _utc_now()
            if status == SearchTaskStatus.RUNNING:
                self._connection.execute(
                    """
                    UPDATE search_tasks
                    SET status = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status.value, now, now, task_id),
                )
            elif status in (
                SearchTaskStatus.COMPLETED,
                SearchTaskStatus.PARTIAL_COMPLETED,
                SearchTaskStatus.FAILED,
                SearchTaskStatus.CANCELLED,
            ):
                self._connection.execute(
                    """
                    UPDATE search_tasks
                    SET status = ?, completed_at = COALESCE(completed_at, ?), updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status.value, now, now, task_id),
                )
            else:
                self._connection.execute(
                    "UPDATE search_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                    (status.value, now, task_id),
                )

    def upsert_source_status(
        self,
        task_id: str,
        source: str,
        status: SourceStatus,
        *,
        error: str | None = None,
        items_count: int = 0,
        ingested_count: int = 0,
        commit: bool = True,
    ) -> None:
        def execute() -> None:
            self._connection.execute(
                """
                INSERT INTO source_status (
                    task_id, source, status, error, items_count, ingested_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, source) DO UPDATE SET
                    status = excluded.status,
                    error = excluded.error,
                    items_count = excluded.items_count,
                    ingested_count = excluded.ingested_count,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    source,
                    status.value,
                    error,
                    items_count,
                    ingested_count,
                    _utc_now(),
                ),
            )

        if commit:
            with self._connection:
                execute()
        else:
            execute()

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        task_row = self._connection.execute(
            """
            SELECT task_id, idempotency_key, status, created_at, started_at,
                   completed_at, updated_at
            FROM search_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if task_row is None:
            return None
        source_rows = self._connection.execute(
            """
            SELECT source, status, error, items_count, ingested_count, updated_at
            FROM source_status
            WHERE task_id = ?
            ORDER BY source
            """,
            (task_id,),
        ).fetchall()
        event_rows = self.list_events(task_id)
        skipped_actions_by_source: dict[str, list[str]] = {}
        last_error = None
        for event in event_rows:
            if event["event_type"] == "search.expansion_skipped_action_not_allowed":
                skipped_actions_by_source.setdefault(event["payload"].get("source"), []).append(
                    event["payload"].get("action")
                )
            if event["event_type"] == "search.source_failed":
                error = event["payload"].get("error")
                last_error = _error_message(error)
            if event["event_type"] == "search.task_failed":
                error = event["payload"].get("error")
                last_error = _error_message(error)
        return {
            "task_id": task_row["task_id"],
            "idempotency_key": task_row["idempotency_key"],
            "status": SearchTaskStatus(task_row["status"]),
            "created_at": task_row["created_at"],
            "started_at": task_row["started_at"],
            "completed_at": task_row["completed_at"],
            "updated_at": task_row["updated_at"],
            "last_error": last_error,
            "source_status": [
                {
                    "source": row["source"],
                    "status": SourceStatus(row["status"]),
                    "error": row["error"],
                    "found_count": row["items_count"],
                    "items_count": row["items_count"],
                    "ingested_count": row["ingested_count"],
                    "rejected_count": max(row["items_count"] - row["ingested_count"], 0),
                    "updated_at": row["updated_at"],
                    "skipped_expansion_actions": skipped_actions_by_source.get(row["source"], []),
                }
                for row in source_rows
            ],
            "sources": {
                row["source"]: {
                    "status": SourceStatus(row["status"]),
                    "error": row["error"],
                    "found_count": row["items_count"],
                    "items_count": row["items_count"],
                    "ingested_count": row["ingested_count"],
                    "rejected_count": max(row["items_count"] - row["ingested_count"], 0),
                    "updated_at": row["updated_at"],
                    "skipped_expansion_actions": skipped_actions_by_source.get(row["source"], []),
                }
                for row in source_rows
            },
        }

    def append_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        commit: bool = True,
    ) -> None:
        def execute() -> None:
            self._connection.execute(
                """
                INSERT INTO events (task_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, event_type, json.dumps(payload or {}, ensure_ascii=True), _utc_now()),
            )

        if commit:
            with self._connection:
                execute()
        else:
            execute()

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT event_id, task_id, event_type, payload_json, created_at
            FROM events
            WHERE task_id = ?
            ORDER BY event_id
            """,
            (task_id,),
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "task_id": row["task_id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_task_ids_by_statuses(self, statuses: Iterable[SearchTaskStatus]) -> list[str]:
        values = [status.value for status in statuses]
        if not values:
            return []
        placeholders = ",".join("?" for _ in values)
        rows = self._connection.execute(
            f"SELECT task_id FROM search_tasks WHERE status IN ({placeholders}) ORDER BY created_at",
            values,
        ).fetchall()
        return [row["task_id"] for row in rows]

    def _ensure_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS search_tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    status TEXT NOT NULL,
                    task_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column("search_tasks", "started_at", "TEXT")
            self._ensure_column("search_tasks", "completed_at", "TEXT")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_status (
                    task_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    items_count INTEGER NOT NULL DEFAULT 0,
                    ingested_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, source),
                    FOREIGN KEY (task_id) REFERENCES search_tasks(task_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES search_tasks(task_id)
                )
                """
            )

    def _ensure_column(self, table_name: str, column_name: str, column_type: str) -> None:
        columns = self._connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(row["name"] == column_name for row in columns):
            return
        self._connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


def _to_json(task: SearchTask) -> str:
    return json.dumps(dataclass_to_dict(task), ensure_ascii=True)


def _task_from_json(raw: str) -> SearchTask:
    data = json.loads(raw)
    return SearchTask(**data)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _error_message(error: Any) -> str | None:
    if error is None:
        return None
    if isinstance(error, dict):
        message = error.get("message")
        if message is not None:
            return str(message)
        code = error.get("code")
        if code is not None:
            return str(code)
    return str(error)
