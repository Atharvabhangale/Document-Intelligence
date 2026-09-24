"""Document endpoints: upload, import from Windchill, list/get/pages/content.

Also hosts the small API test harness (``make_container``, ``FakeIntelligenceService``) used by
the other ``test_api_*`` modules. No network and no real LLM.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from docintel.api.app import create_app
from docintel.api.deps import Container
from docintel.core.config import Settings
from docintel.core.errors import DocumentTooLargeError
from docintel.core.models import DocumentRecord, ExtractedDocument
from docintel.documents import DocumentService
from docintel.extraction.base import TextExtractor
from docintel.providers.llm.base import LLMProvider
from docintel.providers.llm.fake import ScriptedLLMProvider
from docintel.providers.windchill import MockWindchillDocumentProvider
from docintel.providers.windchill.base import WindchillDocumentProvider
from docintel.schemas.report import (
    AskResponse,
    Citation,
    DocumentIntelligenceReport,
    DocumentRef,
    ExecutiveSummary,
    Provenance,
    RequirementsReport,
    RisksReport,
    SummarySection,
    TokenUsage,
    VerificationSummary,
)
from docintel.storage.repository import FileDocumentRepository, InMemoryReportRepository
from pdf_factory import make_pdf
from test_documents_service import FakeExtractor
from test_mock_windchill import write_catalog

MOCK_REF = "mock://wtdocument/SOP-00123/A.3"
MIB = 1024 * 1024

# --- harness ---------------------------------------------------------------------------------


def _provenance(task: str) -> Provenance:
    return Provenance(
        task=task,
        prompt_id=task,
        prompt_version="1",
        provider="scripted",
        model="scripted-model",
        pipeline_version="test",
        extractor="fake-extractor 1.0",
        generated_at=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        duration_ms=1,
        attempts=1,
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def _report_parts(record: DocumentRecord, task: str) -> dict[str, Any]:
    return {
        "report_id": uuid4().hex,
        "document": DocumentRef(
            document_id=record.id,
            source=record.source,
            source_provider=record.source_provider,
            development_only=record.development_only,
            metadata=record.metadata,
            content=record.content,
            page_count=record.extraction.page_count,
        ),
        "citations": [
            Citation(id="C1", page=1, quote="Page one text.", status="verified", match_score=1.0)
        ],
        "verification": VerificationSummary(
            total_citations=1,
            verified=1,
            relocated=0,
            approximate=0,
            unverified=0,
            invalid_page=0,
            items_total=1,
            items_without_verified_source=0,
        ),
        "limitations": [],
        "warnings": [],
        "provenance": _provenance(task),
    }


class FakeIntelligenceService:
    """Duck-typed stand-in for ``DocumentIntelligenceService``.

    Returns minimal valid reports, records every call and raises ``error`` when set, so API
    tests exercise HTTP behaviour rather than the pipeline.
    """

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._cache: dict[tuple[str, str], Any] = {}

    def _call(self, method: str, record: DocumentRecord, **kwargs: Any) -> None:
        self.calls.append((method, record.id, kwargs))
        if self.error is not None:
            raise self.error

    def summarize(
        self, record: DocumentRecord, extracted: ExtractedDocument, *, refresh: bool = False
    ) -> DocumentIntelligenceReport:
        self._call("summarize", record, refresh=refresh, pages=extracted.page_count)
        report = DocumentIntelligenceReport(
            **_report_parts(record, "summarize"),
            summary=SummarySection(
                purpose="Defines maintenance.",
                executive=ExecutiveSummary(text="A <b>summary</b>.", citation_ids=["C1"]),
                key_points=[],
            ),
            requirements=[],
            specifications=[],
            risks=[],
            actions=[],
        )
        self._cache[(record.id, "summarize")] = report
        return report

    def extract_requirements(
        self, record: DocumentRecord, extracted: ExtractedDocument, *, refresh: bool = False
    ) -> RequirementsReport:
        self._call("extract_requirements", record, refresh=refresh)
        report = RequirementsReport(**_report_parts(record, "requirements"), requirements=[])
        self._cache[(record.id, "requirements")] = report
        return report

    def identify_risks(
        self, record: DocumentRecord, extracted: ExtractedDocument, *, refresh: bool = False
    ) -> RisksReport:
        self._call("identify_risks", record, refresh=refresh)
        report = RisksReport(**_report_parts(record, "risks"), risks=[])
        self._cache[(record.id, "risks")] = report
        return report

    def ask(
        self, record: DocumentRecord, extracted: ExtractedDocument, question: str
    ) -> AskResponse:
        self._call("ask", record, question=question)
        parts = _report_parts(record, "ask")
        return AskResponse(
            answer_id=uuid4().hex,
            document_id=record.id,
            question=question,
            answerable=True,
            answer="Every 500 hours.",
            citations=parts["citations"],
            verification=parts["verification"],
            warnings=[],
            provenance=parts["provenance"],
        )

    def cached_report(self, record: DocumentRecord, task: str) -> Any:
        self._call("cached_report", record, task=task)
        return self._cache.get((record.id, task))


def api_settings(settings: Settings, tmp_path: Path, **overrides: Any) -> Settings:
    """Test settings with a temporary mock catalog and a 1 MB upload limit."""
    values: dict[str, Any] = {
        "samples_dir": write_catalog(tmp_path / "samples"),
        "max_upload_mb": 1,
        **overrides,
    }
    return settings.model_copy(update=values)


def make_container(
    settings: Settings,
    *,
    windchill: WindchillDocumentProvider | None = None,
    extractor: TextExtractor | None = None,
    llm: LLMProvider | None = None,
    intelligence: Any | None = None,
) -> Container:
    documents = FileDocumentRepository(settings.data_dir)
    extractor = extractor or FakeExtractor()
    windchill = windchill or MockWindchillDocumentProvider(settings.samples_dir)
    return Container(
        settings=settings,
        documents=documents,
        reports=InMemoryReportRepository(),
        extractor=extractor,
        windchill=windchill,
        llm=llm or ScriptedLLMProvider([]),
        intelligence=intelligence or FakeIntelligenceService(),
        document_service=DocumentService(
            repository=documents, extractor=extractor, windchill=windchill, settings=settings
        ),
    )


def make_client(container: Container, **client_kwargs: Any) -> TestClient:
    return TestClient(create_app(container=container), **client_kwargs)


def upload(client: TestClient, data: bytes, filename: str = "SOP_Test_A.1.pdf", **form: str):
    return client.post(
        "/api/documents", files={"file": (filename, data, "application/pdf")}, data=form
    )


# --- fixtures --------------------------------------------------------------------------------


@pytest.fixture
def container(settings: Settings, tmp_path: Path) -> Container:
    return make_container(api_settings(settings, tmp_path))


@pytest.fixture
def client(container: Container) -> TestClient:
    return make_client(container)


# --- upload ----------------------------------------------------------------------------------


def test_upload_happy_path(client: TestClient, container: Container) -> None:
    data = make_pdf(["Hello"])
    response = upload(client, data)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "source",
        "sourceProvider",
        "developmentOnly",
        "metadata",
        "content",
        "extraction",
        "createdAt",
    }
    assert body["source"] == "upload"
    assert body["developmentOnly"] is True
    assert body["metadata"]["name"] == "SOP Test A.1"
    assert body["content"] == {
        "filename": "SOP_Test_A.1.pdf",
        "mediaType": "application/pdf",
        "sizeBytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "role": "upload",
    }
    assert body["extraction"]["pageCount"] == 2
    assert container.documents.get_content(body["id"]) == data


def test_upload_with_metadata(client: TestClient) -> None:
    metadata = {"number": "SOP-7", "name": "Custom", "state": "Released", "documentType": "SOP"}
    response = upload(client, make_pdf(["x"]), metadata=json.dumps(metadata))
    assert response.status_code == 201
    assert response.json()["metadata"]["number"] == "SOP-7"
    assert response.json()["metadata"]["documentType"] == "SOP"


def test_upload_sanitizes_filename(client: TestClient) -> None:
    response = upload(client, make_pdf(["x"]), filename="../../etc/Evil‮ SOP.pdf")
    assert response.status_code == 201
    assert response.json()["content"]["filename"] == "Evil SOP.pdf"


def test_upload_too_large_file_part(client: TestClient, container: Container) -> None:
    # Body fits in the multipart allowance, but the file itself is over the 1 MB limit.
    response = upload(client, b"%PDF-1.4\n" + b"0" * MIB)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert response.json()["error"]["message"] == ("The document exceeds the maximum size of 1 MB.")
    assert container.documents.list() == []


def test_upload_too_large_body_is_rejected_before_parsing(client: TestClient) -> None:
    response = upload(client, b"%PDF-1.4\n" + b"0" * (2 * MIB))
    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "document_too_large",
        "message": DocumentTooLargeError.default_message,  # from the body size limit
        "retryable": False,
    }


def test_upload_too_large_chunked_body(client: TestClient) -> None:
    boundary = "testboundary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n%PDF-1.4\n"
    ).encode()

    def chunks():
        yield head
        for _ in range(3):
            yield b"0" * MIB  # no Content-Length: the limit is enforced while streaming
        yield f"\r\n--{boundary}--\r\n".encode()

    response = client.post(
        "/api/documents",
        content=chunks(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert response.json()["error"]["message"] == DocumentTooLargeError.default_message


def test_upload_not_a_pdf(client: TestClient) -> None:
    response = upload(client, b"This is plain text, not a PDF.", filename="notes.pdf")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_upload_wrong_extension(client: TestClient) -> None:
    response = upload(client, make_pdf(["x"]), filename="report.docx")
    assert response.status_code == 415


@pytest.mark.parametrize(
    ("metadata", "expected_loc"),
    [
        ("{not json", ["body", "metadata"]),
        (json.dumps({"number": "SOP-1"}), ["body", "metadata", "name"]),
        (json.dumps({"name": "x", "unexpected": 1}), ["body", "metadata", "unexpected"]),
    ],
)
def test_upload_bad_metadata(client: TestClient, metadata: str, expected_loc: list) -> None:
    response = upload(client, make_pdf(["x"]), metadata=metadata)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert expected_loc in [e["loc"] for e in error["details"]["errors"]]
    assert "SOP-1" not in response.text  # submitted values are not echoed


def test_upload_without_file(client: TestClient) -> None:
    response = client.post("/api/documents", data={"metadata": "{}"})
    assert response.status_code == 422
    assert ["body", "file"] in [e["loc"] for e in response.json()["error"]["details"]["errors"]]


# --- import from Windchill -------------------------------------------------------------------


def test_import_from_windchill(client: TestClient) -> None:
    response = client.post("/api/documents/from-windchill", json={"reference": MOCK_REF})
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "windchill"
    assert body["sourceProvider"] == "mock-windchill"
    assert body["developmentOnly"] is True
    assert body["metadata"]["number"] == "SOP-00123"
    assert body["metadata"]["modifiedBy"] == "J. Alvarez"
    assert body["content"]["role"] == "primary"


def test_import_is_idempotent(client: TestClient) -> None:
    first = client.post("/api/documents/from-windchill", json={"reference": MOCK_REF})
    second = client.post("/api/documents/from-windchill", json={"reference": MOCK_REF})
    assert second.status_code == 201
    assert second.json() == first.json()
    assert len(client.get("/api/documents").json()["items"]) == 1


def test_import_unknown_reference(client: TestClient) -> None:
    response = client.post("/api/documents/from-windchill", json={"reference": "mock://nope"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"


@pytest.mark.parametrize("body", [{}, {"reference": 5}, {"reference": "x", "extra": 1}])
def test_import_validation(client: TestClient, body: dict) -> None:
    response = client.post("/api/documents/from-windchill", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_import_blank_reference(client: TestClient) -> None:
    response = client.post("/api/documents/from-windchill", json={"reference": "  "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_import_missing_sample_pdf(settings: Settings, tmp_path: Path) -> None:
    samples = write_catalog(tmp_path / "bare", with_pdfs=False)
    client = make_client(make_container(api_settings(settings, tmp_path, samples_dir=samples)))
    response = client.post("/api/documents/from-windchill", json={"reference": MOCK_REF})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "content_not_available"
    assert "generate_samples.py" in response.json()["error"]["message"]


# --- Windchill browsing ----------------------------------------------------------------------


def test_list_windchill_documents(client: TestClient) -> None:
    body = client.get("/api/windchill/documents").json()
    assert body["provider"] == {"name": "mock-windchill", "developmentOnly": True}
    assert [d["metadata"]["number"] for d in body["items"]] == ["SOP-00123", "SOP-00087"]
    item = body["items"][0]
    assert item["reference"] == MOCK_REF
    assert item["developmentOnly"] is True
    assert item["primaryContent"]["mediaType"] == "application/pdf"


def test_search_windchill_documents(client: TestClient) -> None:
    body = client.get("/api/windchill/documents", params={"q": "lockout", "limit": 5}).json()
    assert [d["metadata"]["number"] for d in body["items"]] == ["SOP-00087"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"q": "x" * 201}])
def test_windchill_list_validation(client: TestClient, params: dict) -> None:
    response = client.get("/api/windchill/documents", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


# --- read back -------------------------------------------------------------------------------


def test_get_list_and_pages(client: TestClient) -> None:
    created = upload(client, make_pdf(["x"])).json()
    imported = client.post("/api/documents/from-windchill", json={"reference": MOCK_REF}).json()

    assert client.get(f"/api/documents/{created['id']}").json() == created
    items = client.get("/api/documents").json()["items"]
    assert [i["id"] for i in items] == [imported["id"], created["id"]]  # newest first
    assert len(client.get("/api/documents", params={"limit": 1}).json()["items"]) == 1

    pages = client.get(f"/api/documents/{created['id']}/pages").json()
    assert pages["documentId"] == created["id"]
    assert [p["number"] for p in pages["pages"]] == [1, 2]
    assert pages["pages"][0] == {
        "number": 1,
        "text": "Page one text.",
        "charCount": 14,
        "hasTextLayer": True,
        "needsOcr": False,
    }


def test_list_limit_validation(client: TestClient) -> None:
    assert client.get("/api/documents", params={"limit": 0}).status_code == 422


def test_content_headers(client: TestClient) -> None:
    data = make_pdf(["x"])
    created = upload(client, data, filename="Prüfung SOP_A.1.pdf").json()
    response = client.get(f"/api/documents/{created['id']}/content")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        "inline; filename=\"Pr_fung SOP_A.1.pdf\"; filename*=UTF-8''Pr%C3%BCfung%20SOP_A.1.pdf"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private"
    assert response.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"


@pytest.mark.parametrize("suffix", ["", "/pages", "/content"])
def test_unknown_document(client: TestClient, suffix: str) -> None:
    response = client.get(f"/api/documents/{'f' * 32}{suffix}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"


@pytest.mark.parametrize(
    "document_id", ["not-an-id", "F" * 32, "a" * 31, "a" * 33, "a" * 31 + "g", "%2E%2E"]
)
def test_malformed_document_id(client: TestClient, document_id: str) -> None:
    response = client.get(f"/api/documents/{document_id}/pages")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"
