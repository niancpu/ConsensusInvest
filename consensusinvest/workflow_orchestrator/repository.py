"""In-memory Workflow repository for the MVP orchestrator."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from .models import (
    WorkflowEventRecord,
    WorkflowProgress,
    WorkflowRunRecord,
)


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRunRecord] = {}
        self._events: dict[str, list[WorkflowEventRecord]] = {}
        self._next_run_id = 1

    def create_run(self, run: WorkflowRunRecord) -> WorkflowRunRecord:
        self._runs[run.workflow_run_id] = run
        self._events.setdefault(run.workflow_run_id, [])
        return run

    def new_workflow_run_id(self, *, ticker: str, analysis_time: datetime) -> str:
        value = self._next_run_id
        self._next_run_id += 1
        return f"wr_{analysis_time.strftime('%Y%m%d')}_{ticker}_{value:06d}"

    def get_run(self, workflow_run_id: str) -> WorkflowRunRecord | None:
        return self._runs.get(workflow_run_id)

    def update_run(self, workflow_run_id: str, **changes: object) -> WorkflowRunRecord:
        current = self._runs[workflow_run_id]
        updated = replace(current, **changes)
        self._runs[workflow_run_id] = updated
        return updated

    def list_runs(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WorkflowRunRecord], int]:
        rows = list(self._runs.values())
        if ticker is not None:
            rows = [row for row in rows if row.ticker == ticker]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    def append_event(
        self,
        workflow_run_id: str,
        event_type: str,
        payload: dict | None = None,
        *,
        created_at: datetime | None = None,
    ) -> WorkflowEventRecord:
        events = self._events.setdefault(workflow_run_id, [])
        sequence = len(events) + 1
        event = WorkflowEventRecord(
            event_id=f"evt_{workflow_run_id}_{sequence:06d}",
            workflow_run_id=workflow_run_id,
            sequence=sequence,
            event_type=event_type,
            created_at=created_at or datetime.now(UTC),
            payload=dict(payload or {}),
        )
        events.append(event)
        return event

    def list_events(self, workflow_run_id: str, *, after_sequence: int | None = None) -> list[WorkflowEventRecord]:
        rows = list(self._events.get(workflow_run_id, []))
        if after_sequence is not None:
            rows = [row for row in rows if row.sequence > after_sequence]
        return rows

    def last_event_sequence(self, workflow_run_id: str) -> int:
        events = self._events.get(workflow_run_id, [])
        return events[-1].sequence if events else 0


__all__ = ["InMemoryWorkflowRepository", "WorkflowProgress", "WorkflowRunRecord"]
