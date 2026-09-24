"""Analysis endpoints and error mapping, with a fake intelligence service (no LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docintel.core.config import Settings
from docintel.core.errors import (
    AIConfigurationError,
    AIOutputTruncatedError,
    AIOutputValidationError,
    AIRateLimitError,
    AIRefusalError,
    AITimeoutError,
    InvalidRequestError,
    NoExtractableTextError,
)
from test_api_documents import (
    MOCK_REF,
    FakeIntelligenceService,
    api_settings,
    make_client,
    make_container,
)

TASK_ENDPOINTS = [
    ("summarize", "summarize", "summarize"),
    ("requirements", "extract_requirements", "requirements"),
    ("risks", "identify_risks", "risks"),
]


def _client(
    settings: Settings, tmp_path: Path, intelligence: FakeIntelligenceService, **client_kwargs
) -> tuple[TestClient, str]:
    """Client plus the id of an imported mock document."""
    container = make_container(api_settings(settings, tmp_path), intelligence=intelligence)
    client = make_client(container, **client_kwargs)
    document = client.post("/api/documents/from-windchill", json={"reference": MOCK_REF})
    assert document.status_code == 201
    return client, document.json()["id"]


@pytest.fixture
def intelligence() -> FakeIntelligenceService:
    return FakeIntelligenceService()


@pytest.fixture
def api(
    settings: Settings, tmp_path: Path, intelligence: FakeIntelligenceService
) -> tuple[TestClient, str]:
    return _client(settings, tmp_path, intelligence)


# --- happy paths -----------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "method", "task"), TASK_ENDPOINTS)
def test_report_endpoints(
    api: tuple[TestClient, str],
    intelligence: FakeIntelligenceService,
    path: str,
    method: str,
    task: str,
) -> None:
    client, document_id = api
    response = client.post(f"/api/documents/{document_id}/{path}")

    assert response.status_code == 200
    body = response.json()
    assert body["task"] == task
    assert body["schemaVersion"] == "1.0"
    assert body["document"]["documentId"] == document_id
    assert body["document"]["developmentOnly"] is True
    assert body["provenance"]["task"] == task
    assert intelligence.calls[-1][:2] == (method, document_id)
    assert intelligence.calls[-1][2]["refresh"] is False


@pytest.mark.parametrize(("path", "method", "_task"), TASK_ENDPOINTS)
def test_refresh_flag_is_passed_through(
    api: tuple[TestClient, str],
    intelligence: FakeIntelligenceService,
    path: str,
    method: str,
    _task: str,
) -> None:
    client, document_id = api
    assert client.post(f"/api/documents/{document_id}/{path}?refresh=true").status_code == 200
    assert intelligence.calls[-1][:2] == (method, document_id)
    assert intelligence.calls[-1][2]["refresh"] is True


def test_refresh_must_be_boolean(api: tuple[TestClient, str]) -> None:
    client, document_id = api
    response = client.post(f"/api/documents/{document_id}/summarize?refresh=maybe")
    assert response.status_code == 422


def test_summary_text_is_returned_as_plain_json_string(api: tuple[TestClient, str]) -> None:
    client, document_id = api
    response = client.post(f"/api/documents/{document_id}/summarize")
    assert response.headers["content-type"] == "application/json"
    assert response.json()["summary"]["executive"]["text"] == "A <b>summary</b>."


def test_summarize_receives_stored_extraction(
    api: tuple[TestClient, str], intelligence: FakeIntelligenceService
) -> None:
    client, document_id = api
    client.post(f"/api/documents/{document_id}/summarize")
    assert intelligence.calls[-1][2]["pages"] == 2


@pytest.mark.parametrize(("path", "_method", "task"), TASK_ENDPOINTS)
def test_cached_report(api: tuple[TestClient, str], path: str, _method: str, task: str) -> None:
    client, document_id = api
    missing = client.get(f"/api/documents/{document_id}/reports/{task}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "report_not_found"

    created = client.post(f"/api/documents/{document_id}/{path}").json()
    cached = client.get(f"/api/documents/{document_id}/reports/{task}")
    assert cached.status_code == 200
    assert cached.json() == created


def test_cached_report_unknown_task(api: tuple[TestClient, str]) -> None:
    client, document_id = api
    response = client.get(f"/api/documents/{document_id}/reports/ask")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_ask(api: tuple[TestClient, str], intelligence: FakeIntelligenceService) -> None:
    client, document_id = api
    response = client.post(
        f"/api/documents/{document_id}/ask", json={"question": "How often is the filter changed?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["documentId"] == document_id
    assert body["answerable"] is True
    assert body["question"] == "How often is the filter changed?"
    assert intelligence.calls[-1] == (
        "ask",
        document_id,
        {"question": "How often is the filter changed?"},
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # no body
        {"json": {}},
        {"json": {"question": ""}},
        {"json": {"question": 42}},
        {"json": {"question": "ok", "extra": True}},
        {"content": b"{broken", "headers": {"Content-Type": "application/json"}},
    ],
)
def test_ask_validation(
    api: tuple[TestClient, str], intelligence: FakeIntelligenceService, kwargs: dict
) -> None:
    client, document_id = api
    response = client.post(f"/api/documents/{document_id}/ask", **kwargs)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["retryable"] is False
    assert all(set(e) == {"loc", "msg"} for e in error["details"]["errors"])
    assert not [c for c in intelligence.calls if c[0] == "ask"]


# --- document lookup -------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["summarize", "requirements", "risks", "ask", "reports/summarize"])
@pytest.mark.parametrize("document_id", ["0" * 32, "not-a-valid-id"])
def test_unknown_or_malformed_document(
    api: tuple[TestClient, str], path: str, document_id: str
) -> None:
    client, _ = api
    method = client.get if path.startswith("reports/") else client.post
    kwargs = {"json": {"question": "Why?"}} if path == "ask" else {}
    response = method(f"/api/documents/{document_id}/{path}", **kwargs)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"


# --- error mapping ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "status", "code", "retryable"),
    [
        (AIRateLimitError(), 429, "ai_rate_limited", True),
        (AIOutputValidationError(), 502, "ai_output_invalid", True),
        (AIOutputTruncatedError(), 502, "ai_output_truncated", True),
        (NoExtractableTextError(), 422, "no_extractable_text", False),
        (AIRefusalError(), 422, "ai_refused", False),
        (AITimeoutError(), 504, "ai_timeout", True),
        (AIConfigurationError(), 503, "ai_not_configured", False),
        (InvalidRequestError("The question is too long."), 400, "invalid_request", False),
    ],
)
def test_domain_errors_are_mapped(
    settings: Settings,
    tmp_path: Path,
    error: Exception,
    status: int,
    code: str,
    retryable: bool,
) -> None:
    client, document_id = _client(settings, tmp_path, FakeIntelligenceService(error=error))
    response = client.post(f"/api/documents/{document_id}/summarize")

    assert response.status_code == status
    assert response.json() == {
        "error": {"code": code, "message": error.message, "retryable": retryable}
    }
    if code == "ai_rate_limited":
        assert response.headers["retry-after"] == "10"
    else:
        assert "retry-after" not in response.headers


def test_error_details_are_included(settings: Settings, tmp_path: Path) -> None:
    error = AIOutputValidationError(details={"attempts": 2})
    client, document_id = _client(settings, tmp_path, FakeIntelligenceService(error=error))
    body = client.post(f"/api/documents/{document_id}/risks").json()
    assert body["error"]["details"] == {"attempts": 2}


def test_unhandled_exception_is_generic_500(
    settings: Settings, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret_text = "Hydraulic pressure 210 bar confidential"
    client, document_id = _client(
        settings, tmp_path, FakeIntelligenceService(error=RuntimeError(secret_text))
    )
    with caplog.at_level("INFO"):
        response = client.post(f"/api/documents/{document_id}/summarize")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred. Please try again later.",
            "retryable": False,
        }
    }
    assert secret_text not in response.text
    request_id = response.headers["x-request-id"]
    unhandled = [r for r in caplog.records if r.getMessage().startswith("Unhandled")]
    assert len(unhandled) == 1
    assert "builtins.RuntimeError" in unhandled[0].getMessage()
    assert request_id in unhandled[0].getMessage()
    assert all(secret_text not in r.getMessage() for r in caplog.records)
    # Security headers are present on the generic error too.
    assert response.headers["x-content-type-options"] == "nosniff"
