"""HTTP middleware (pure ASGI).

Stack, outermost first (see ``app.create_app``)::

    RequestContextMiddleware   request id, access log line, security headers
    CORSMiddleware             configured origins only
    ErrorBoundaryMiddleware    unhandled exception -> generic 500 JSON (with CORS headers)
    BodySizeLimitMiddleware    hard cap on the request body size
    (FastAPI exception handlers and routes)

Access log lines contain the method, path (never the query string), status, duration and
request id; never headers or bodies.
"""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from docintel.api.errors import (
    REQUEST_ID_STATE_KEY,
    error_response,
    http_error_response,
    internal_error_response,
    log_unhandled_exception,
    request_id_of,
)
from docintel.core.errors import DocumentTooLargeError

access_logger = logging.getLogger("docintel.api.access")

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_MAX_LOGGED_PATH_CHARS = 200

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
)

#: Added to every response unless the route already set the header (the PDF content route
#: sends its own Content-Security-Policy).
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
)


class RequestContextMiddleware:
    """Assign a request id, add security headers and write one access log line per request.

    A sane incoming ``X-Request-ID`` (``[A-Za-z0-9-]{1,64}``) is kept so ids can be correlated
    across a proxy; anything else is replaced by a new random id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid4().hex
        scope.setdefault("state", {})[REQUEST_ID_STATE_KEY] = request_id
        started = time.perf_counter()
        status_code = 500  # reported if the response never starts

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in SECURITY_HEADERS:
                    if name not in headers:
                        headers[name] = value
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            access_logger.info(
                "%s %s %d %.1fms request_id=%s",
                scope.get("method", "-"),
                _loggable_path(scope),
                status_code,
                (time.perf_counter() - started) * 1000,
                request_id,
            )


class ErrorBoundaryMiddleware:
    """Answer unhandled exceptions with the generic ``internal_error`` body.

    Sits inside the CORS middleware so the error is readable by allowed cross-origin clients.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if response_started:
                raise  # too late for an error body; let the server abort the response
            if isinstance(exc, StarletteHTTPException):
                response = http_error_response(exc)
            else:
                log_unhandled_exception(exc, request_id_of(scope))
                response = internal_error_response()
            await response(scope, receive, send)


class RequestBodyTooLargeError(StarletteHTTPException):
    """Raised while reading a request body that exceeds the configured limit."""

    def __init__(self) -> None:
        super().__init__(status_code=413)


class BodySizeLimitMiddleware:
    """Reject request bodies larger than ``max_body_bytes`` without buffering them.

    A declared ``Content-Length`` above the limit is answered with 413 before the body is
    read. Otherwise the body is counted as it streams in, and reading stops with 413 as soon as
    the limit is exceeded (chunked uploads included), so at most ``max_body_bytes`` are ever
    buffered by the multipart parser.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_body_bytes:
            response = error_response(
                413, DocumentTooLargeError.code, DocumentTooLargeError.default_message
            )
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise RequestBodyTooLargeError()
            return message

        await self.app(scope, limited_receive, send)


def _incoming_request_id(scope: Scope) -> str | None:
    value = Headers(scope=scope).get(REQUEST_ID_HEADER)
    return value if value is not None and _REQUEST_ID_RE.fullmatch(value) else None


def _content_length(scope: Scope) -> int | None:
    value = Headers(scope=scope).get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _loggable_path(scope: Scope) -> str:
    path = str(scope.get("path", ""))
    if len(path) > _MAX_LOGGED_PATH_CHARS:
        path = path[:_MAX_LOGGED_PATH_CHARS] + "..."
    return path.encode("unicode_escape").decode("ascii")
