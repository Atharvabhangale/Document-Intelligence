"""Security headers, CORS, request ids, access logging and HTTP error mapping."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from docintel.api.middleware import (
    CONTENT_SECURITY_POLICY,
    BodySizeLimitMiddleware,
    RequestBodyTooLargeError,
)
from docintel.core.config import Settings
from test_api_documents import (
    FakeIntelligenceService,
    api_settings,
    make_client,
    make_container,
)

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
)
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "SAMEORIGIN",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "content-security-policy": EXPECTED_CSP,
}
ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture
def client(settings: Settings, tmp_path: Path) -> TestClient:
    return make_client(make_container(api_settings(settings, tmp_path)))


def _assert_security_headers(response) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get(name) == value, name


def test_csp_constant_matches_policy() -> None:
    assert CONTENT_SECURITY_POLICY == EXPECTED_CSP


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("get", "/api/health", 200),
        ("get", "/", 200),
        ("get", "/api/windchill/documents", 200),
        ("get", "/api/nope", 404),
        ("get", f"/api/documents/{'a' * 32}", 404),
        ("post", "/api/documents/from-windchill", 422),
        ("delete", "/api/health", 405),
    ],
)
def test_security_headers_on_every_response(
    client: TestClient, method: str, path: str, status: int
) -> None:
    response = client.request(method.upper(), path, json={} if method == "post" else None)
    assert response.status_code == status
    _assert_security_headers(response)


def test_security_headers_on_unhandled_error(settings: Settings, tmp_path: Path) -> None:
    container = make_container(
        api_settings(settings, tmp_path),
        intelligence=FakeIntelligenceService(error=ValueError("boom")),
    )
    client = make_client(container)
    document = client.post(
        "/api/documents/from-windchill", json={"reference": "mock://wtdocument/SOP-00123/A.3"}
    ).json()
    response = client.post(
        f"/api/documents/{document['id']}/risks", headers={"Origin": ALLOWED_ORIGIN}
    )
    assert response.status_code == 500
    _assert_security_headers(response)
    assert re.fullmatch(r"[a-f0-9]{32}", response.headers["x-request-id"])
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


# --- HTTP error mapping ----------------------------------------------------------------------


def test_unknown_route_is_json_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "retryable": False,
        }
    }


def test_wrong_method_is_json_405(client: TestClient) -> None:
    response = client.put("/api/documents")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert response.headers["allow"]  # Starlette lists the first matching route's methods


def test_malformed_multipart_is_400(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        content=b"garbage",
        headers={"Content-Type": "multipart/form-data"},  # no boundary
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_validation_errors_do_not_echo_input(client: TestClient) -> None:
    probe = "<script>alert('probe-value')</script>"
    response = client.post("/api/documents/from-windchill", json={"reference": {"x": probe}})
    assert response.status_code == 422
    assert "probe-value" not in response.text


def test_oversized_request_is_rejected_by_content_length(client: TestClient) -> None:
    response = client.post(
        "/api/documents/from-windchill",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(50 * 1024 * 1024)},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    _assert_security_headers(response)


def test_body_limit_stops_reading_once_exceeded() -> None:
    chunks = [b"x" * 6, b"x" * 6, b"x" * 6, b"x" * 6]
    consumed = 0

    async def receive() -> dict:
        nonlocal consumed
        consumed += 1
        more = consumed < len(chunks)
        return {"type": "http.request", "body": chunks[consumed - 1], "more_body": more}

    async def app(scope, receive, send) -> None:
        while (await receive()).get("more_body"):
            pass

    async def send(message) -> None:
        raise AssertionError("the middleware must not answer; the route's handler does")

    async def run() -> None:
        middleware = BodySizeLimitMiddleware(app, max_body_bytes=10)
        with pytest.raises(RequestBodyTooLargeError):
            await middleware({"type": "http", "headers": []}, receive, send)

    anyio.run(run)
    assert consumed == 2  # stopped at the chunk that crossed the limit


# --- CORS ------------------------------------------------------------------------------------


def test_cors_allowed_origin(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in response.headers
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_cors_disallowed_origin(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight(client: TestClient) -> None:
    allowed = client.options(
        "/api/documents",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert set(allowed.headers["access-control-allow-methods"].split(", ")) == {"GET", "POST"}

    wrong_method = client.options(
        "/api/documents",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "DELETE"},
    )
    assert wrong_method.status_code == 400

    wrong_origin = client.options(
        "/api/documents",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert wrong_origin.status_code == 400
    assert "access-control-allow-origin" not in wrong_origin.headers


# --- request ids and access log --------------------------------------------------------------


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "abc-123-DEF"})
    assert response.headers["x-request-id"] == "abc-123-DEF"


@pytest.mark.parametrize("incoming", ["x" * 65, "bad id", "id;drop", "ünïcode".encode(), ""])
def test_insane_request_id_is_replaced(client: TestClient, incoming: str | bytes) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": incoming})
    assert re.fullmatch(r"[a-f0-9]{32}", response.headers["x-request-id"])


def test_request_id_is_generated(client: TestClient) -> None:
    first = client.get("/api/health").headers["x-request-id"]
    second = client.get("/api/health").headers["x-request-id"]
    assert re.fullmatch(r"[a-f0-9]{32}", first)
    assert first != second


def test_access_log_line(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="docintel.api.access"):
        response = client.get(
            "/api/windchill/documents",
            params={"q": "confidential search text"},
            headers={"X-Request-ID": "req-42"},
        )
    assert response.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "docintel.api.access"]
    assert len(lines) == 1
    assert re.fullmatch(r"GET /api/windchill/documents 200 \d+\.\dms request_id=req-42", lines[0])
    assert "confidential" not in lines[0]


def test_access_log_escapes_control_characters(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="docintel.api.access"):
        client.get("/api/x%0Afake-log-line")
    lines = [r.getMessage() for r in caplog.records if r.name == "docintel.api.access"]
    assert lines and "\n" not in lines[0]


def test_logs_never_contain_the_api_key(
    settings: Settings, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from docintel.providers.llm.factory import create_llm_provider

    key = settings.anthropic_api_key.get_secret_value()
    client = make_client(
        make_container(api_settings(settings, tmp_path), llm=create_llm_provider(settings))
    )
    with caplog.at_level(logging.DEBUG):
        client.get("/api/health")
        client.get("/api/nope")
    assert caplog.records
    assert all(key not in r.getMessage() for r in caplog.records)
