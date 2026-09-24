"""DocumentService: upload ingestion and idempotent import from a Windchill provider."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from conftest import make_extracted
from docintel.core.config import Settings
from docintel.core.errors import (
    DocumentNotFoundError,
    DocumentTooLargeError,
    EncryptedDocumentError,
    InvalidRequestError,
    UnsupportedMediaTypeError,
)
from docintel.core.models import (
    DocumentMetadata,
    DocumentSource,
    ExtractedDocument,
    Requester,
)
from docintel.documents import (
    DocumentService,
    humanize_filename,
    looks_like_pdf,
    pdf_filename,
    sanitize_filename,
)
from docintel.extraction.base import TextExtractor
from docintel.providers.windchill import MockWindchillDocumentProvider
from docintel.providers.windchill.base import (
    DocumentContent,
    WindchillDocument,
    WindchillDocumentProvider,
)
from docintel.storage.repository import FileDocumentRepository
from pdf_factory import make_pdf
from test_mock_windchill import write_catalog

REQUESTER = Requester(user_id="dev.user", display_name="Development User")
MOCK_REF = "mock://wtdocument/SOP-00123/A.3"


class FakeExtractor(TextExtractor):
    """Returns canned pages (or raises ``error``) and records every call."""

    name = "fake-extractor 1.0"

    def __init__(self, pages: list[str] | None = None, error: Exception | None = None) -> None:
        self.pages = pages or ["Page one text.", "Page two text."]
        self.error = error
        self.calls: list[tuple[bytes, int]] = []

    def extract(self, data: bytes, *, max_pages: int) -> ExtractedDocument:
        self.calls.append((data, max_pages))
        if self.error is not None:
            raise self.error
        return make_extracted(self.pages, extractor=self.name)


class RecordingProvider(WindchillDocumentProvider):
    """Provider double that serves one document and records the requester of every call."""

    name = "recording"
    development_only = False

    def __init__(self, data: bytes, media_type: str = "application/pdf") -> None:
        self.data = data
        self.media_type = media_type
        self.metadata = DocumentMetadata(number="DOC-1", name="Recorded", revision="B")
        self.requesters: list[Requester] = []

    def list_documents(self, *, requester, query=None, limit=50):
        raise NotImplementedError

    def get_document(self, reference: str, *, requester: Requester) -> WindchillDocument:
        self.requesters.append(requester)
        return WindchillDocument(
            reference=reference,
            metadata=self.metadata,
            development_only=False,
        )

    def get_primary_content(self, reference: str, *, requester: Requester) -> DocumentContent:
        self.requesters.append(requester)
        return DocumentContent(
            filename="../evil/Recorded.pdf", media_type=self.media_type, data=self.data
        )


@pytest.fixture
def small_settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={"max_upload_mb": 1, "max_pages": 7, "samples_dir": write_catalog(tmp_path / "s")}
    )


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def repository(small_settings: Settings) -> FileDocumentRepository:
    return FileDocumentRepository(small_settings.data_dir)


def make_service(
    settings: Settings,
    repository: FileDocumentRepository,
    extractor: TextExtractor,
    windchill: WindchillDocumentProvider | None = None,
) -> DocumentService:
    return DocumentService(
        repository=repository,
        extractor=extractor,
        windchill=windchill or MockWindchillDocumentProvider(settings.samples_dir),
        settings=settings,
    )


@pytest.fixture
def service(
    small_settings: Settings, repository: FileDocumentRepository, extractor: FakeExtractor
) -> DocumentService:
    return make_service(small_settings, repository, extractor)


# --- uploads ---------------------------------------------------------------------------------


def test_ingest_upload_happy_path(
    service: DocumentService, repository: FileDocumentRepository, extractor: FakeExtractor
) -> None:
    data = make_pdf(["Hello"])
    record = service.ingest_upload("SOP-00999_Pump_Check_A.1.pdf", data)

    assert len(record.id) == 32 and int(record.id, 16) >= 0
    assert record.source is DocumentSource.UPLOAD
    assert record.source_provider == "upload"
    assert record.development_only is True
    assert record.metadata.name == "SOP-00999 Pump Check A.1"
    assert record.content.filename == "SOP-00999_Pump_Check_A.1.pdf"
    assert record.content.media_type == "application/pdf"
    assert record.content.role == "upload"
    assert record.content.size_bytes == len(data)
    assert record.content.sha256 == hashlib.sha256(data).hexdigest()
    assert record.extraction.page_count == 2
    assert record.extraction.extractor == "fake-extractor 1.0"
    assert extractor.calls == [(data, 7)]  # max_pages from settings

    assert repository.get(record.id) == record
    assert repository.get_content(record.id) == data
    assert repository.get_extracted(record.id).pages[0].text == "Page one text."


def test_each_upload_gets_a_new_id(service: DocumentService) -> None:
    data = make_pdf(["Same"])
    assert service.ingest_upload("a.pdf", data).id != service.ingest_upload("a.pdf", data).id


def test_upload_uses_supplied_metadata(service: DocumentService) -> None:
    metadata = DocumentMetadata(number="SOP-1", name="Supplied name", state="Released")
    record = service.ingest_upload("x.pdf", make_pdf(["x"]), metadata=metadata)
    assert record.metadata == metadata


def test_upload_too_large(service: DocumentService, extractor: FakeExtractor) -> None:
    data = b"%PDF-1.4\n" + b"0" * (1024 * 1024)
    with pytest.raises(DocumentTooLargeError) as info:
        service.ingest_upload("big.pdf", data)
    assert "1 MB" in info.value.message
    assert extractor.calls == []


def test_upload_at_limit_is_accepted(service: DocumentService) -> None:
    data = b"%PDF-1.4\n" + b"0" * (1024 * 1024 - 9)
    assert service.ingest_upload("limit.pdf", data).content.size_bytes == 1024 * 1024


@pytest.mark.parametrize(
    ("filename", "data", "media_type"),
    [
        ("notes.pdf", b"just some text", None),
        ("page.pdf", b"<html><script>alert(1)</script></html>", "application/pdf"),
        ("report.docx", None, None),
        ("image.png", None, "application/pdf"),
        ("sop.pdf", None, "text/html"),
        ("sop.pdf", None, "image/png"),
    ],
)
def test_upload_rejects_non_pdf(
    service: DocumentService,
    extractor: FakeExtractor,
    filename: str,
    data: bytes | None,
    media_type: str | None,
) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        service.ingest_upload(filename, data or make_pdf(["x"]), media_type=media_type)
    assert extractor.calls == []


@pytest.mark.parametrize(
    "media_type",
    [None, "", "application/pdf", "Application/PDF; charset=binary", "application/octet-stream"],
)
def test_upload_accepts_pdf_compatible_media_types(
    service: DocumentService, media_type: str | None
) -> None:
    assert service.ingest_upload("ok.pdf", make_pdf(["x"]), media_type=media_type)


def test_extraction_errors_propagate_and_nothing_is_saved(
    small_settings: Settings, repository: FileDocumentRepository
) -> None:
    service = make_service(
        small_settings, repository, FakeExtractor(error=EncryptedDocumentError())
    )
    with pytest.raises(EncryptedDocumentError):
        service.ingest_upload("locked.pdf", make_pdf(["x"]))
    assert repository.list() == []


# --- file names ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SOP-00123_A.3.pdf", "SOP-00123_A.3.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\me\\My  SOP.pdf", "My SOP.pdf"),
        ("evil\r\nX-Injected: 1.pdf", "evilX-Injected_ 1.pdf"),
        ("\u202efdp.exe", "fdp.exe"),  # bidi override removed
        ('a<b>c:"d"|e?f*.pdf', "a_b_c__d__e_f_.pdf"),
        ("  .hidden.pdf.  ", "hidden.pdf"),
        ("Qualitätsprüfung.pdf", "Qualitätsprüfung.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
        ("../..", "document.pdf"),
        ("\x00\x01", "document.pdf"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_limits_length_and_keeps_extension() -> None:
    name = sanitize_filename("x" * 500 + ".pdf")
    assert len(name) == 200
    assert name.endswith(".pdf")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a.pdf", "a.pdf"),
        ("A.PDF", "A.PDF"),
        ("blob", "blob.pdf"),
        ("SOP-00123_A.3", "SOP-00123_A.3.pdf"),
        (None, "document.pdf"),
    ],
)
def test_pdf_filename(raw: str | None, expected: str) -> None:
    assert pdf_filename(raw) == expected


@pytest.mark.parametrize("raw", ["x.docx", "x.html", "x.pdf.exe", "archive.tar.gz"])
def test_pdf_filename_rejects_other_types(raw: str) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        pdf_filename(raw)


def test_humanize_filename() -> None:
    assert humanize_filename("SOP-00123_Machine__Maintenance_A.3.pdf") == (
        "SOP-00123 Machine Maintenance A.3"
    )
    assert humanize_filename("___.pdf") == "Untitled document"


def test_looks_like_pdf() -> None:
    assert looks_like_pdf(b"%PDF-1.7\n...")
    assert looks_like_pdf(b"\xef\xbb\xbf\r\n %PDF-1.4")
    assert not looks_like_pdf(b"PK\x03\x04")
    assert not looks_like_pdf(b"")


# --- import from Windchill -------------------------------------------------------------------


def test_import_from_mock_windchill(
    service: DocumentService,
    repository: FileDocumentRepository,
    extractor: FakeExtractor,
    small_settings: Settings,
) -> None:
    record = service.import_from_windchill(MOCK_REF, requester=REQUESTER)

    data = (small_settings.samples_dir / "SOP-00123_Machine_Maintenance_A.3.pdf").read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    assert record.id == hashlib.sha256(f"mock-windchill|{MOCK_REF}|{sha}".encode()).hexdigest()[:32]
    assert record.source is DocumentSource.WINDCHILL
    assert record.source_provider == "mock-windchill"
    assert record.development_only is True
    assert record.metadata.number == "SOP-00123"
    assert record.metadata.version_label == "A.3"
    assert record.metadata.source_ref == MOCK_REF
    assert record.content.role == "primary"
    assert record.content.sha256 == sha
    assert record.content.filename == "SOP-00123_Machine_Maintenance_A.3.pdf"
    assert extractor.calls == [(data, 7)]
    assert repository.get(record.id) == record


def test_import_is_idempotent(service: DocumentService, extractor: FakeExtractor) -> None:
    first = service.import_from_windchill(MOCK_REF, requester=REQUESTER)
    second = service.import_from_windchill(f"  {MOCK_REF} ", requester=REQUESTER)
    assert second == first  # same id, same created_at: the stored record is returned
    assert len(extractor.calls) == 1


def test_reimport_refreshes_changed_metadata_without_reextraction(
    small_settings: Settings, repository: FileDocumentRepository, extractor: FakeExtractor
) -> None:
    provider = RecordingProvider(make_pdf(["same content"]))
    service = make_service(small_settings, repository, extractor, provider)
    first = service.import_from_windchill("wt-ref-1", requester=REQUESTER)

    released = provider.metadata.model_copy(update={"state": "Released"})
    provider.metadata = released  # e.g. a lifecycle "Set State": same iteration, same content
    second = service.import_from_windchill("wt-ref-1", requester=REQUESTER)

    assert second.id == first.id
    assert second.created_at == first.created_at
    assert second.metadata.state == "Released"
    assert repository.get(first.id).metadata.state == "Released"
    assert repository.get_extracted(first.id).page_count == 2
    assert len(extractor.calls) == 1


def test_import_passes_requester_and_sanitizes_provider_filename(
    small_settings: Settings, repository: FileDocumentRepository, extractor: FakeExtractor
) -> None:
    provider = RecordingProvider(make_pdf(["x"]))
    record = make_service(small_settings, repository, extractor, provider).import_from_windchill(
        "wt-ref-1", requester=REQUESTER
    )
    assert provider.requesters == [REQUESTER, REQUESTER]
    assert record.development_only is False
    assert record.source_provider == "recording"
    assert record.content.filename == "Recorded.pdf"
    assert record.metadata.source_ref == "wt-ref-1"  # filled in when the provider has none


def test_import_new_content_gets_new_id(
    small_settings: Settings, repository: FileDocumentRepository, extractor: FakeExtractor
) -> None:
    provider = RecordingProvider(make_pdf(["first iteration"]))
    service = make_service(small_settings, repository, extractor, provider)
    first = service.import_from_windchill("wt-ref-1", requester=REQUESTER)
    provider.data = make_pdf(["second iteration"])
    assert service.import_from_windchill("wt-ref-1", requester=REQUESTER).id != first.id


@pytest.mark.parametrize("media_type", ["application/msword", "text/plain", ""])
def test_import_rejects_non_pdf_content(
    small_settings: Settings,
    repository: FileDocumentRepository,
    extractor: FakeExtractor,
    media_type: str,
) -> None:
    provider = RecordingProvider(make_pdf(["x"]), media_type=media_type)
    with pytest.raises(UnsupportedMediaTypeError):
        make_service(small_settings, repository, extractor, provider).import_from_windchill(
            "wt-ref", requester=REQUESTER
        )


def test_import_rejects_pdf_media_type_without_pdf_bytes(
    small_settings: Settings, repository: FileDocumentRepository, extractor: FakeExtractor
) -> None:
    provider = RecordingProvider(b"<html>not a pdf</html>")
    with pytest.raises(UnsupportedMediaTypeError):
        make_service(small_settings, repository, extractor, provider).import_from_windchill(
            "wt-ref", requester=REQUESTER
        )


def test_import_too_large(
    small_settings: Settings, repository: FileDocumentRepository, extractor: FakeExtractor
) -> None:
    provider = RecordingProvider(b"%PDF-1.4\n" + b"0" * (1024 * 1024))
    with pytest.raises(DocumentTooLargeError):
        make_service(small_settings, repository, extractor, provider).import_from_windchill(
            "wt-ref", requester=REQUESTER
        )
    assert extractor.calls == []


@pytest.mark.parametrize("reference", ["", "   ", "x" * 1025, "ref\nwith-newline"])
def test_import_rejects_invalid_reference(service: DocumentService, reference: str) -> None:
    with pytest.raises(InvalidRequestError):
        service.import_from_windchill(reference, requester=REQUESTER)


def test_import_unknown_reference(service: DocumentService) -> None:
    with pytest.raises(DocumentNotFoundError):
        service.import_from_windchill("mock://wtdocument/NOPE/Z.9", requester=REQUESTER)
