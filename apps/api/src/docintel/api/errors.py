"""Uniform JSON error responses.

Every error leaves the API as ``ErrorResponse``::

    {"error": {"code": "...", "message": "...", "retryable": false, "details": {...}}}

* ``DocIntelError`` subclasses map to their own ``code`` / ``http_status`` / ``retryable``.
* Request validation errors map to ``422 invalid_request``; ``details`` lists only field
  locations and messages, never the submitted values.
* Starlette HTTP errors (unknown route, wrong method, body too large, ...) map to their status
  with a generic message.
* Anything else is a ``500 internal_error`` with a generic message. The exception type and
  stack are logged with the request id; the exception message is not logged because messages
  from third-party libraries can quote document content.
"""

from __future__ import annotations

import http
import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response
from starlette.types import Scope

from docintel.core.errors import AIRateLimitError, DocIntelError, DocumentTooLargeError
from docintel.schemas.api import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)

#: Key of the request id in the ASGI scope state (set by ``RequestContextMiddleware``).
REQUEST_ID_STATE_KEY = "request_id"

RATE_LIMIT_RETRY_AFTER_SECONDS = 10

_HTTP_ERROR_CODES: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: DocumentTooLargeError.code,
    415: "unsupported_media_type",
}
_HTTP_ERROR_MESSAGES: dict[int, str] = {
    400: "The request could not be processed.",
    404: "The requested resource was not found.",
    405: "The request method is not allowed for this resource.",
    413: DocumentTooLargeError.default_message,
}
_INTERNAL_ERROR_MESSAGE = "An unexpected error occurred. Please try again later."


def request_id_of(scope: Scope) -> str | None:
    """The request id assigned by ``RequestContextMiddleware``, if any."""
    state = scope.get("state")
    return state.get(REQUEST_ID_STATE_KEY) if isinstance(state, dict) else None


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, retryable=retryable, details=details or None)
    )
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True), status_code=status_code, headers=headers
    )


def internal_error_response() -> JSONResponse:
    return error_response(500, "internal_error", _INTERNAL_ERROR_MESSAGE)


def http_error_response(exc: StarletteHTTPException) -> Response:
    status = exc.status_code
    if status in {204, 304}:
        return Response(status_code=status, headers=exc.headers)
    try:
        phrase = http.HTTPStatus(status).phrase
    except ValueError:
        phrase = "HTTP error"
    return error_response(
        status,
        _HTTP_ERROR_CODES.get(status, "http_error"),
        _HTTP_ERROR_MESSAGES.get(status, f"{phrase}."),
        headers=exc.headers,
    )


def log_unhandled_exception(exc: BaseException, request_id: str | None) -> None:
    """Log an unexpected exception: type and stack frames only (see module docstring)."""
    frames = "".join(traceback.format_tb(exc.__traceback__))
    logger.error(
        "Unhandled %s.%s request_id=%s\n%s",
        type(exc).__module__,
        type(exc).__qualname__,
        request_id or "-",
        frames.rstrip(),
    )


# --- exception handlers ----------------------------------------------------------------------


async def docintel_error_handler(request: Request, exc: DocIntelError) -> Response:
    level = logging.WARNING if exc.http_status >= 500 else logging.INFO
    logger.log(
        level,
        "Request failed: code=%s status=%d request_id=%s",
        exc.code,
        exc.http_status,
        request_id_of(request.scope) or "-",
    )
    headers = (
        {"Retry-After": str(RATE_LIMIT_RETRY_AFTER_SECONDS)}
        if isinstance(exc, AIRateLimitError)
        else None
    )
    return error_response(
        exc.http_status,
        exc.code,
        exc.message,
        retryable=exc.retryable,
        details=exc.details,
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
    errors = [
        {"loc": [_loc_part(part) for part in err.get("loc", ())], "msg": str(err.get("msg", ""))}
        for err in exc.errors()
    ]
    return error_response(
        422, "invalid_request", "The request is invalid.", details={"errors": errors}
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    return http_error_response(exc)


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Last-resort handler (normally ``ErrorBoundaryMiddleware`` answers first)."""
    log_unhandled_exception(exc, request_id_of(request.scope))
    return internal_error_response()


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DocIntelError, docintel_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def _loc_part(part: Any) -> str | int:
    return part if isinstance(part, int) else str(part)
