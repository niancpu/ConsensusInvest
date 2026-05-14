import gzip
import json
from datetime import datetime, timezone

from consensusinvest.runtime import RuntimeEvent, SQLiteRuntimeEventRepository


def _event(
    *,
    event_id: str,
    event_type: str,
    occurred_at: datetime,
    payload: dict,
    correlation_id: str = "corr_archive_001",
    workflow_run_id: str | None = "wr_archive_001",
    producer: str = "agent_swarm",
) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        workflow_run_id=workflow_run_id,
        producer=producer,
        payload=payload,
    )


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 10, 0, tzinfo=timezone.utc)


def _read_jsonl_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as archive_file:
        return [json.loads(line) for line in archive_file if line.strip()]


def test_runtime_event_archive_skips_non_terminal_groups(tmp_path):
    repository = SQLiteRuntimeEventRepository(tmp_path / "runtime_events.sqlite3")
    repository.append_event(
        _event(
            event_id="evt_unfinished_started",
            event_type="started",
            occurred_at=_utc(2025, 1, 10),
            payload={"agent_run_id": "ar_unfinished", "status": "running"},
        )
    )
    repository.append_event(
        _event(
            event_id="evt_unfinished_progress",
            event_type="status_changed",
            occurred_at=_utc(2025, 1, 11),
            payload={"agent_run_id": "ar_unfinished", "status": "running"},
        )
    )

    result = repository.archive_events(
        cutoff=_utc(2025, 2, 1),
        archive_dir=tmp_path / "archive",
        batch_id="batch001",
    )

    assert result.archived_count == 0
    assert result.deleted_count == 0
    assert result.archive_files == ()
    assert [event.event_id for event in repository.list_events()] == [
        "evt_unfinished_started",
        "evt_unfinished_progress",
    ]
    repository.close()


def test_runtime_event_archive_writes_readable_jsonl_and_deletes_archived_events(tmp_path):
    repository = SQLiteRuntimeEventRepository(tmp_path / "runtime_events.sqlite3")
    repository.append_event(
        _event(
            event_id="evt_terminal_started",
            event_type="started",
            occurred_at=_utc(2025, 1, 10),
            payload={"agent_run_id": "ar_done", "status": "running"},
        )
    )
    repository.append_event(
        _event(
            event_id="evt_terminal_progress",
            event_type="status_changed",
            occurred_at=_utc(2025, 1, 11),
            payload={"agent_run_id": "ar_done", "status": "running"},
        )
    )
    repository.append_event(
        _event(
            event_id="evt_terminal_completed",
            event_type="completed",
            occurred_at=_utc(2025, 2, 1),
            payload={"agent_run_id": "ar_done", "status": "completed"},
        )
    )
    repository.append_event(
        _event(
            event_id="evt_task_terminal_started",
            event_type="started",
            occurred_at=_utc(2025, 2, 2),
            payload={"task_id": "task_done", "status": "running"},
        )
    )
    repository.append_event(
        _event(
            event_id="evt_task_terminal_failed",
            event_type="status_changed",
            occurred_at=_utc(2025, 2, 3),
            payload={"task_id": "task_done", "status": "failed"},
        )
    )
    repository.append_event(
        _event(
            event_id="evt_hot_recent",
            event_type="completed",
            occurred_at=_utc(2025, 4, 1),
            payload={"agent_run_id": "ar_recent", "status": "completed"},
        )
    )

    result = repository.archive_events(
        cutoff=_utc(2025, 3, 1),
        archive_dir=tmp_path / "archive",
        batch_id="batch001",
    )

    assert result.archived_count == 5
    assert result.deleted_count == 5
    assert [path.name for path in result.archive_files] == [
        "runtime_events_2025-01_batch001.jsonl.gz",
        "runtime_events_2025-02_batch001.jsonl.gz",
    ]

    january_records = _read_jsonl_gzip(result.archive_files[0])
    february_records = _read_jsonl_gzip(result.archive_files[1])
    assert [record["event_id"] for record in january_records] == [
        "evt_terminal_started",
        "evt_terminal_progress",
    ]
    assert [record["event_id"] for record in february_records] == [
        "evt_terminal_completed",
        "evt_task_terminal_started",
        "evt_task_terminal_failed",
    ]
    assert january_records[0] == {
        "event_id": "evt_terminal_started",
        "event_type": "started",
        "occurred_at": "2025-01-10T10:00:00+00:00",
        "correlation_id": "corr_archive_001",
        "workflow_run_id": "wr_archive_001",
        "producer": "agent_swarm",
        "payload": {"agent_run_id": "ar_done", "status": "running"},
    }
    assert [event.event_id for event in repository.list_events()] == ["evt_hot_recent"]
    repository.close()
