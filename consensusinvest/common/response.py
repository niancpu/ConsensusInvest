"""Standard response envelopes used across the API.

The shape comes from `docs/web_api/overview.md`:

- success: `{"data": ..., "meta": {"request_id": "..."}}`
- list:    `{"data": [...], "pagination": {...}, "meta": {...}}`
- error:   `{"error": {"code": "...", "message": "...", "details": {...}}, "meta": {...}}`
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


def new_request_id() -> str:
    """Return a request id of the form req_YYYYMMDD_HHMMSS_<short>."""
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"req_{now}_{uuid4().hex[:6]}"


class Meta(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    data_state: str | None = None
    refresh_task_id: str | None = None
    report_run_id: str | None = None


class SingleResponse(BaseModel, Generic[T]):
    data: T
    meta: Meta = Field(default_factory=Meta)


class ListPagination(BaseModel):
    limit: int | None = None
    offset: int | None = None
    page: int | None = None
    page_size: int | None = None
    total: int
    has_more: bool | None = None


class ListResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: ListPagination | None = None
    meta: Meta = Field(default_factory=Meta)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
    meta: Meta = Field(default_factory=Meta)
