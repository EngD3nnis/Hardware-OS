"""Domain exceptions + DRF exception handler that normalises error shape."""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """Base class for business-rule violations raised by the service layer."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "A domain error occurred."
    code = "domain_error"

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Resource not found."
    code = "not_found"


class PermissionDeniedError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "You do not have permission to perform this action."
    code = "permission_denied"


class ValidationError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_message = "Validation failed."
    code = "validation_error"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_message = "The request conflicts with the current state."
    code = "conflict"


class InsufficientStockError(ConflictError):
    default_message = "Insufficient stock to complete the operation."
    code = "insufficient_stock"


def api_exception_handler(exc, context):
    """
    Unifies error responses to:
        {"error": {"code": "...", "message": "...", "details": {...}}}
    """
    if isinstance(exc, DomainError):
        return Response(
            {"error": {"code": exc.code, "message": exc.message, "details": {}}},
            status=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = response.data
        message = detail.get("detail") if isinstance(detail, dict) else None
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "error"),
                "message": str(message) if message else "Request failed.",
                "details": detail if not message else {},
            }
        }
    return response
