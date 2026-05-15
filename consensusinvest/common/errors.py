"""API-level errors and FastAPI error handler installation.

Error codes follow `docs/web_api/appendix.md` §17.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .response import ErrorBody, ErrorResponse, Meta

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base API error mapped to the documented error envelope."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if http_status is not None:
            self.http_status = http_status
        if code is not None:
            self.code = code

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(error=ErrorBody(code=self.code, message=self.message, details=self.details))


class ValidationError(ApiError):
    code = "INVALID_REQUEST"
    http_status = 400


class NotFoundError(ApiError):
    code = "STOCK_NOT_FOUND"
    http_status = 404


class BoundaryViolationError(ApiError):
    code = "BOUNDARY_VIOLATION"
    http_status = 409


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_response().model_dump(exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(
                code="INVALID_REQUEST",
                message="Request validation failed.",
                details={"errors": exc.errors()},
            ),
            meta=Meta(),
        )
        return JSONResponse(status_code=400, content=body.model_dump(exclude_none=True))

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path, exc_info=exc)
        body = ErrorResponse(
            error=ErrorBody(
                code="INTERNAL_ERROR",
                message="服务器处理失败，请查看后端日志；如果是本地运行，先确认模型和数据源密钥是否已配置。",
                details={"path": request.url.path},
            ),
            meta=Meta(),
        )
        return JSONResponse(status_code=500, content=body.model_dump(exclude_none=True))
