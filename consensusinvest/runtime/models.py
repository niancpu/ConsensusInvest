"""Shared runtime models for internal module calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Common async task status values."""

    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL_COMPLETED = "partial_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class InternalError:
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InternalCallEnvelope:
    request_id: str
    correlation_id: str
    workflow_run_id: str | None
    analysis_time: datetime
    requested_by: str
    idempotency_key: str | None = None
    trace_level: str | None = None

    def validate_for_create(self) -> None:
        """Validate envelope fields required by create-style internal calls."""
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required for create calls")


@dataclass(frozen=True, slots=True)
class AsyncTaskReceipt:
    task_id: str
    status: TaskStatus
    accepted_at: datetime
    idempotency_key: str
    poll_after_ms: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: str
    event_type: str
    occurred_at: datetime
    correlation_id: str
    workflow_run_id: str | None
    producer: str
    payload: dict[str, Any] = field(default_factory=dict)
