"""Shared helpers for Report Module view assembly."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from consensusinvest.runtime import InternalCallEnvelope

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def _dedupe(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item not in seen:
            seen[item] = None
    return list(seen.keys())

def _query_envelope() -> InternalCallEnvelope:
    return InternalCallEnvelope(
        request_id="req_report_api_query",
        correlation_id="corr_report_api_query",
        workflow_run_id=None,
        analysis_time=datetime.now(timezone.utc),
        requested_by="report_module",
    )

def _dt(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""

def _comparable_dt(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)

def _jsonable(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return dict(asdict(value))
    return dict(value)
