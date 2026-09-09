"""Convenience wrappers around api_response_toolkit for ChatPilot views.

Usage in views:
    from common.api_response import api_success, api_error, api_paginated, ApiError

    return api_success(data, "User fetched")
    return api_error("Not found", code="NOT_FOUND", status_code=404)
    raise ApiError.NotFound("User not found")
"""
from rest_framework.response import Response
from api_response_toolkit.drf.responses import (
    success as _success,
    error as _error,
    paginated as _paginated,
    validation_error as _validation_error,
)
from api_response_toolkit.exceptions import (
    NotFoundError,
    ValidationError,
    UnauthorizedError,
    ForbiddenError,
    ConflictError,
    BadRequestError,
    APIException,
)


def api_success(data=None, message=None, status_code=200, meta=None):
    """Return a standardized success DRF Response."""
    return _success(data=data, message=message, status_code=status_code, meta=meta)


def api_error(message, code=None, status_code=400, details=None, errors=None):
    """Return a standardized error DRF Response."""
    return _error(message=message, code=code, status_code=status_code, data=details, errors=errors)


def api_paginated(data, page=1, limit=20, total=0, message=None):
    """Return a standardized paginated DRF Response."""
    return _paginated(data=data, page=page, limit=limit, total=total, message=message)


def api_validation_error(errors, message="Validation failed", details=None):
    """Return a standardized validation error DRF Response."""
    return _validation_error(errors=errors, message=message, details=details)


class ApiError:
    """Convenience namespace for raising typed API exceptions."""
    NotFound = NotFoundError
    Validation = ValidationError
    Unauthorized = UnauthorizedError
    Forbidden = ForbiddenError
    Conflict = ConflictError
    BadRequest = BadRequestError
    Internal = APIException
