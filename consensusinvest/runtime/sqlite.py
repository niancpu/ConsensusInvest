"""SQLAlchemy-backed SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import RLock, local
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool


@dataclass(slots=True)
class SQLAlchemySQLiteHandle:
    connection: "LockedSQLiteConnection"
    engine: Engine
    _pooled_connection: Any

    def close(self) -> None:
        self._pooled_connection.close()
        self.engine.dispose()


class LockedSQLiteConnection:
    """Small thread-serializing facade for a shared SQLite DBAPI connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = RLock()
        self._state = local()

    def __enter__(self) -> "LockedSQLiteConnection":
        self._lock.acquire()
        self._connection.__enter__()
        self._state.depth = self._context_depth + 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        try:
            return self._connection.__exit__(exc_type, exc, traceback)
        finally:
            self._state.depth = max(self._context_depth - 1, 0)
            self._lock.release()

    @property
    def _context_depth(self) -> int:
        return int(getattr(self._state, "depth", 0))

    def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor | "LockedSQLiteCursor":
        self._lock.acquire()
        try:
            cursor = self._connection.execute(*args, **kwargs)
            if self._context_depth > 0 or cursor.description is None:
                self._lock.release()
                return cursor
            return LockedSQLiteCursor(cursor, self._lock)
        except Exception:
            self._lock.release()
            raise

    def executemany(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.executemany(*args, **kwargs)

    def executescript(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.executescript(*args, **kwargs)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class LockedSQLiteCursor:
    """Cursor proxy that releases the connection lock after result consumption."""

    def __init__(self, cursor: sqlite3.Cursor, lock: RLock) -> None:
        self._cursor = cursor
        self._lock = lock
        self._released = False

    def fetchone(self) -> sqlite3.Row | tuple[Any, ...] | None:
        try:
            return self._cursor.fetchone()
        finally:
            self._release()

    def fetchall(self) -> list[sqlite3.Row] | list[tuple[Any, ...]]:
        try:
            return self._cursor.fetchall()
        finally:
            self._release()

    def fetchmany(self, size: int | None = None) -> list[sqlite3.Row] | list[tuple[Any, ...]]:
        try:
            if size is None:
                return self._cursor.fetchmany()
            return self._cursor.fetchmany(size)
        finally:
            self._release()

    def close(self) -> None:
        try:
            self._cursor.close()
        finally:
            self._release()

    def _release(self) -> None:
        if not self._released:
            self._released = True
            self._lock.release()

    def __iter__(self) -> Any:
        try:
            yield from self._cursor
        finally:
            self._release()

    def __enter__(self) -> "LockedSQLiteCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self._release()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


def open_sqlite_connection(db_path: str | Path) -> SQLAlchemySQLiteHandle:
    """Create a SQLite DBAPI connection through SQLAlchemy.

    Repositories in this codebase still use explicit SQL and sqlite3.Row mapping.
    SQLAlchemy owns URL parsing and connection options here, while callers retain
    the DBAPI connection to keep the current repository contracts small.
    """
    path = str(db_path)
    connect_args: dict[str, object] = {"check_same_thread": False}
    kwargs: dict[str, object] = {"connect_args": connect_args}
    if path == ":memory:":
        kwargs["poolclass"] = StaticPool
        url = "sqlite+pysqlite:///:memory:"
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+pysqlite:///{path}"

    engine = create_engine(url, **kwargs)
    pooled = engine.raw_connection()
    raw_connection = pooled.driver_connection
    raw_connection.row_factory = sqlite3.Row
    return SQLAlchemySQLiteHandle(
        connection=LockedSQLiteConnection(raw_connection),
        engine=engine,
        _pooled_connection=pooled,
    )


__all__ = ["LockedSQLiteConnection", "SQLAlchemySQLiteHandle", "open_sqlite_connection"]
