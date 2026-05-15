"""Search Agent task status API."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, Depends, Request

from consensusinvest.common.errors import NotFoundError
from consensusinvest.common.response import SingleResponse
from consensusinvest.runtime.wiring import AppRuntime

router = APIRouter(prefix="/api/v1", tags=["search_agent"])


def get_search_pool(request: Request) -> Any:
    runtime: AppRuntime = request.app.state.runtime
    return runtime.search_pool


@router.get("/search-tasks/{task_id}", response_model=SingleResponse[dict[str, Any]])
def get_search_task_status(
    task_id: str,
    search_pool: Any = Depends(get_search_pool),
) -> SingleResponse[dict[str, Any]]:
    status = search_pool.get_status(None, task_id)
    if is_dataclass(status):
        status = asdict(status)
    if isinstance(status, dict) and (
        status.get("error") == "search_task_not_found" or status.get("code") == "search_task_not_found"
    ):
        raise NotFoundError(
            f"Search task not found: {task_id}",
            code="SEARCH_TASK_NOT_FOUND",
            details={"task_id": task_id},
        )
    return SingleResponse(data=status)
