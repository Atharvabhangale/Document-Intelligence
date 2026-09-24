"""Document ingestion: register uploaded or provider documents with the intelligence service.

Ingestion validates the content (size, PDF signature), extracts page-aware text once, and
stores the original bytes, the extracted pages and a ``DocumentRecord`` in the document
repository. Analysis tasks later work from the stored extraction.

* Uploads are a DEVELOPMENT path (``development_only=True``); each upload gets a new random id.
* Provider imports get a deterministic id derived from provider, reference and content hash,
  so importing the same document iteration again returns the existing record without
  re-extracting it. Content is always fetched from the provider on behalf of the requester, so
  a real provider authorizes every import.

Logs contain identifiers, sizes and counts only, never file names or document text.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from docintel.core.config import Settings
from docintel.core.errors import (
    DocumentTooLargeError,
    InvalidRequestError,
    UnsupportedMediaTypeError,
)
from docintel.core.models import (
    ContentFile,
    DocumentMetadata,
    DocumentRecord,
    DocumentSource,
    ExtractedDocument,
    ExtractionSummary,
    Requester,
)
from docintel.providers.windchill.base import WindchillDocumentProvider
from docintel.storage.repository import DocumentRepository

if TYPE_CHECKING:
    # Type-only: importing the extraction package loads the PDF libraries.
    from docintel.extraction.base import TextExtractor

logger = logging.getLogger(__name__)

PDF_MEDIA_TYPE = "application/pdf"
DEFAULT_FILENAME = "document.pdf"
MAX_FILENAME_CHARS = 200
MAX_REFERENCE_CHARS = 1024

# Declared upload media types that do not contradict a PDF: none, PDF, or the generic types
# browsers and tools send for unknown files. The PDF signature check is the authority.
_UPLOAD_MEDIA_TYPES = frozenset(
    {"", PDF_MEDIA_TYPE, "application/x-pdf", "application/octet-stream", "binary/octet-stream"}
)
_PDF_MAGIC = b"%PDF-"
_PDF_HEADER_WINDOW = 1024
_UTF8_BOM = b"\xef\xbb\xbf"

# Characters that are unsafe in file names on common platforms (path separators are handled
# separately by taking the basename).
_RESERVED_CHARS_RE = re.compile(r'[<>:"|?*]')
_WHITESPACE_RE = re.compile(r"\s+")
# An extension that names another file type (".docx", ".html"), as opposed to a Windchill-style
# version suffix such as ".3" in "SOP-00123_A.3".
_FOREIGN_EXTENSION_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


class DocumentService:
    def __init__(
        self,
        *,
        repository: DocumentRepository,
        extractor: TextExtractor,
        windchill: WindchillDocumentProvider,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._extractor = extractor
        self._windchill = windchill
        self._settings = settings

    def ingest_upload(
        self,
        filename: str,
        data: bytes,
        *,
        metadata: DocumentMetadata | None = None,
        media_type: str | None = None,
    ) -> DocumentRecord:
        """Register an uploaded PDF (DEVELOPMENT path).

        Args:
            filename: client-supplied file name; sanitized before it is stored.
            data: the complete file content.
            metadata: optional business metadata; defaults to a name derived from the file name.
            media_type: the declared media type, if any (must not contradict a PDF).

        Raises:
            DocumentTooLargeError: ``data`` exceeds the upload limit (or the page limit).
            UnsupportedMediaTypeError: the file is not a PDF.
            ExtractionError: text extraction failed (including encrypted PDFs).
        """
        self._check_size(data)
        safe_name = pdf_filename(filename)
        if _base_media_type(media_type) not in _UPLOAD_MEDIA_TYPES or not looks_like_pdf(data):
            raise UnsupportedMediaTypeError()

        extracted = self._extract(data)
        record = DocumentRecord(
            id=uuid4().hex,
            source=DocumentSource.UPLOAD,
            source_provider="upload",
            development_only=True,
            metadata=metadata or DocumentMetadata(name=humanize_filename(safe_name)),
            content=ContentFile(
                filename=safe_name,
                media_type=PDF_MEDIA_TYPE,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                role="upload",
            ),
            extraction=ExtractionSummary.from_extracted(extracted),
            created_at=datetime.now(UTC),
        )
        self._repository.save(record, data, extracted)
        self._log_ingested(record)
        return record

    def import_from_windchill(self, reference: str, *, requester: Requester) -> DocumentRecord:
        """Register the primary content of a provider document, on behalf of ``requester``.

        Idempotent: the id is derived from provider, reference and content hash, so a repeated
        import of unchanged content returns the stored record without re-extraction. Its
        metadata is refreshed from the provider when it changed: in Windchill a lifecycle state
        change (e.g. In Work -> Released) does not create a new iteration or new content.

        Raises:
            InvalidRequestError: ``reference`` is empty, too long or contains control characters.
            DocumentNotFoundError / AccessDeniedError / ContentNotAvailableError /
            WindchillProviderError: raised by the provider.
            UnsupportedMediaTypeError: the primary content is not a PDF.
            DocumentTooLargeError: the content exceeds the size (or page) limit.
            ExtractionError: text extraction failed.
        """
        reference = _validate_reference(reference)
        provider = self._windchill
        document = provider.get_document(reference, requester=requester)
        content = provider.get_primary_content(reference, requester=requester)
        if _base_media_type(content.media_type) != PDF_MEDIA_TYPE:
            raise UnsupportedMediaTypeError()
        data = content.data
        self._check_size(data)
        if not looks_like_pdf(data):
            raise UnsupportedMediaTypeError()

        sha256 = hashlib.sha256(data).hexdigest()
        identity = f"{provider.name}|{reference}|{sha256}".encode()
        document_id = hashlib.sha256(identity).hexdigest()[:32]
        metadata = document.metadata
        if metadata.source_ref is None:
            metadata = metadata.model_copy(update={"source_ref": reference})

        if self._repository.exists(document_id):
            return self._refresh_metadata(self._repository.get(document_id), metadata, data)

        extracted = self._extract(data)
        record = DocumentRecord(
            id=document_id,
            source=DocumentSource.WINDCHILL,
            source_provider=provider.name,
            development_only=provider.development_only,
            metadata=metadata,
            content=ContentFile(
                filename=sanitize_filename(content.filename),
                media_type=PDF_MEDIA_TYPE,
                size_bytes=len(data),
                sha256=sha256,
                role="primary",
            ),
            extraction=ExtractionSummary.from_extracted(extracted),
            created_at=datetime.now(UTC),
        )
        self._repository.save(record, data, extracted)
        self._log_ingested(record)
        return record

    # --- internals -------------------------------------------------------------------------

    def _refresh_metadata(
        self, existing: DocumentRecord, metadata: DocumentMetadata, data: bytes
    ) -> DocumentRecord:
        """The stored record, with ``metadata`` saved if it differs (extraction is reused)."""
        if existing.metadata == metadata:
            logger.info("Document already imported: id=%s", existing.id)
            return existing
        updated = existing.model_copy(update={"metadata": metadata})
        self._repository.save(updated, data, self._repository.get_extracted(existing.id))
        logger.info("Document metadata refreshed from provider: id=%s", existing.id)
        return updated

    def _check_size(self, data: bytes) -> None:
        if len(data) > self._settings.max_upload_bytes:
            raise DocumentTooLargeError(
                f"The document exceeds the maximum size of {self._settings.max_upload_mb} MB."
            )

    def _extract(self, data: bytes) -> ExtractedDocument:
        return self._extractor.extract(data, max_pages=self._settings.max_pages)

    @staticmethod
    def _log_ingested(record: DocumentRecord) -> None:
        logger.info(
            "Document ingested: id=%s source=%s provider=%s bytes=%d pages=%d chars=%d",
            record.id,
            record.source.value,
            record.source_provider,
            record.content.size_bytes,
            record.extraction.page_count,
            record.extraction.total_chars,
        )


# --- helpers ---------------------------------------------------------------------------------


def looks_like_pdf(data: bytes) -> bool:
    """True when ``data`` starts with a PDF header (after an optional BOM / whitespace)."""
    head = data[:_PDF_HEADER_WINDOW]
    head = head.removeprefix(_UTF8_BOM)
    return head.lstrip(b" \t\r\n\x00\x0c").startswith(_PDF_MAGIC)


def sanitize_filename(raw: str | None, *, default: str = DEFAULT_FILENAME) -> str:
    """A safe display/storage file name derived from a client- or provider-supplied name.

    Keeps only the last path component (``/`` and ``\\`` both count as separators), removes
    control and invisible formatting characters (including bidirectional overrides), replaces
    characters reserved on common file systems, collapses whitespace, trims leading/trailing
    dots and spaces and limits the length to ``MAX_FILENAME_CHARS`` (keeping the extension).
    Returns ``default`` if nothing usable remains. The result is never used as a path.
    """
    name = unicodedata.normalize("NFC", raw or "")
    name = re.split(r"[\\/]", name)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = _RESERVED_CHARS_RE.sub("_", name)
    name = _WHITESPACE_RE.sub(" ", name).strip(" .")
    if not name:
        return default
    return _truncate(name, MAX_FILENAME_CHARS)


def pdf_filename(raw: str | None) -> str:
    """Sanitized upload file name that ends in ``.pdf``.

    Raises:
        UnsupportedMediaTypeError: the name carries another file type's extension.
    """
    name = sanitize_filename(raw)
    if name.lower().endswith(".pdf"):
        return name
    if _FOREIGN_EXTENSION_RE.search(name):
        raise UnsupportedMediaTypeError()
    return _truncate(f"{name}.pdf", MAX_FILENAME_CHARS)


def humanize_filename(filename: str) -> str:
    """Default document name from a file name: the stem with underscores as spaces."""
    stem = filename[:-4] if filename.lower().endswith(".pdf") else filename
    name = _WHITESPACE_RE.sub(" ", stem.replace("_", " ")).strip()
    return name or "Untitled document"


def _truncate(name: str, limit: int) -> str:
    if len(name) <= limit:
        return name
    stem, dot, ext = name.rpartition(".")
    if dot and 0 < len(ext) <= 16 and stem:
        return f"{stem[: limit - len(ext) - 1].rstrip(' .')}.{ext}"
    return name[:limit]


def _base_media_type(media_type: str | None) -> str:
    return (media_type or "").split(";", 1)[0].strip().lower()


def _validate_reference(reference: str) -> str:
    reference = reference.strip()
    if not reference or len(reference) > MAX_REFERENCE_CHARS or _CONTROL_CHARS_RE.search(reference):
        raise InvalidRequestError("The document reference is invalid.")
    return reference
