"""Custom DRF renderer that wraps all responses in the standardized envelope.

Responses already containing a `success` key (from api_success/api_error) are
passed through unchanged.  Raw serializer data is wrapped as:
    {success: true, message: "Success", data: <raw>}
"""
from rest_framework.renderers import JSONRenderer


class StandardizedJSONRenderer(JSONRenderer):
    """Wrap every DRF response in the standardized API envelope."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # If already wrapped (api_success/api_error/api_paginated), pass through
        if isinstance(data, dict) and "success" in data:
            return super().render(data, accepted_media_type, renderer_context)

        # If it's an error dict from DRF (e.g. {"detail": "..."}), pass through
        # — the exception handler already wraps those.
        if isinstance(data, dict) and "error" in data and "success" not in data:
            return super().render(data, accepted_media_type, renderer_context)

        response = renderer_context.get("response") if renderer_context else None
        status_code = response.status_code if response else 200

        # Wrap raw data in success envelope
        if 200 <= status_code < 300:
            wrapped = {
                "success": True,
                "message": "Success",
                "data": data,
            }
        else:
            # Error response — wrap as error
            wrapped = {
                "success": False,
                "message": str(data) if data else "Error",
                "code": "ERROR",
            }

        return super().render(wrapped, accepted_media_type, renderer_context)
