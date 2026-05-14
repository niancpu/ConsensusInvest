"""Shared API plumbing — response envelopes, error model, request IDs."""

from .errors import ApiError, BoundaryViolationError, NotFoundError, ValidationError, install_error_handlers
from .response import (
    ErrorBody,
    ErrorResponse,
    ListPagination,
    ListResponse,
    Meta,
    SingleResponse,
    new_request_id,
)

__all__ = [
    "ApiError",
    "BoundaryViolationError",
    "ErrorBody",
    "ErrorResponse",
    "ListPagination",
    "ListResponse",
    "Meta",
    "NotFoundError",
    "SingleResponse",
    "ValidationError",
    "install_error_handlers",
    "new_request_id",
]
