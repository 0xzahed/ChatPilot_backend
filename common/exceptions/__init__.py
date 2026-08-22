from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        data = {
            "success": False,
            "error": {
                "code": getattr(exc, "code", None) or response.status_code,
                "message": str(exc),
                "details": response.data if isinstance(response.data, dict) else None,
            },
        }
        # Flatten validation errors
        if isinstance(response.data, dict) and "detail" not in response.data:
            data["error"]["details"] = response.data
        response.data = data
    return response


class AppError(Exception):
    """Application-level error with a message and optional code."""

    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)
