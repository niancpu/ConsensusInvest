"""API-level errors and FastAPI error handler installation.

Error codes follow `docs/web_api/appendix.md` §17.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .response import ErrorBody, ErrorResponse, Meta


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
