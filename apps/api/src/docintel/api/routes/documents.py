"""Register documents (upload, import from Windchill) and read them back.

Both registration endpoints return ``201 Created``. Importing from Windchill is idempotent: a
repeated import of unchanged content returns the existing record (same deterministic id), still
with ``201`` so clients handle a single success status.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError

from docintel.api.deps import ContainerDep, DocumentRecordDep, RequesterDep
from docintel.core.models import DocumentMetadata, DocumentRecord
from docintel.documents import PDF_MEDIA_TYPE, sanitize_filename
from docintel.schemas.api import DocumentList, DocumentPages, ImportFromWindchillRequest

router = APIRouter(prefix="/api/documents", tags=["documents"])

METADATA_MAX_CHARS = 16 * 1024

# The PDF response is not HTML, so the page-level CSP directives do not apply to it; a strict
# policy (object-src/sandbox) can stop browsers' built-in PDF viewers from rendering it. Only
# framing is restricted: the document may be embedded by this application alone.
PDF_CONTENT_SECURITY_POLICY = "frame-ancestors 'self'"


@router.post("", status_code=201, response_model=DocumentRecord)
async def upload_document(
    container: ContainerDep,
    file: Annotated[UploadFile, File(description="The PDF document.")],
    metadata: Annotated[
        str | None,
        Form(
            max_length=METADATA_MAX_CHARS,
            description="Optional document metadata as a JSON object (DocumentMetadata).",
        ),
    ] = None,
) -> DocumentRecord:
    """Upload a PDF for analysis (DEVELOPMENT path: records are marked development-only)."""
    parsed_metadata = _parse_metadata(metadata)
    # The request body is already capped by BodySizeLimitMiddleware. Read at most one byte more
    # than the limit so the service can reject oversized files without reading them fully.
    data = await file.read(container.settings.max_upload_bytes + 1)
    return await run_in_threadpool(
        container.document_service.ingest_upload,
        file.filename or "",
        data,
        metadata=parsed_metadata,
        media_type=file.content_type,
    )


@router.post("/from-windchill", status_code=201, response_model=DocumentRecord)
def import_from_windchill(
    body: ImportFromWindchillRequest, container: ContainerDep, requester: RequesterDep
) -> DocumentRecord:
    """Import a document's primary content from the configured Windchill provider."""
    return container.document_service.import_from_windchill(body.reference, requester=requester)


@router.get("", response_model=DocumentList)
def list_documents(
    container: ContainerDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> DocumentList:
    """Registered documents, most recent first."""
    return DocumentList(items=container.documents.list(limit))


@router.get("/{document_id}", response_model=DocumentRecord)
def get_document(record: DocumentRecordDep) -> DocumentRecord:
    return record


@router.get("/{document_id}/pages", response_model=DocumentPages)
def get_document_pages(record: DocumentRecordDep, container: ContainerDep) -> DocumentPages:
    """The extracted text of every page (1-based physical page numbers)."""
    extracted = container.documents.get_extracted(record.id)
    return DocumentPages(document_id=record.id, pages=extracted.pages)


@router.get(
    "/{document_id}/content",
    response_class=Response,
    responses={200: {"content": {PDF_MEDIA_TYPE: {}}, "description": "The original PDF."}},
)
def get_document_content(record: DocumentRecordDep, container: ContainerDep) -> Response:
    """The original PDF bytes, for display inline in the browser."""
    return Response(
        content=container.documents.get_content(record.id),
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": content_disposition(record.content.filename),
            "Cache-Control": "private",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": PDF_CONTENT_SECURITY_POLICY,
        },
    )


def content_disposition(filename: str, disposition: str = "inline") -> str:
    """``Content-Disposition`` value with an ASCII fallback and an RFC 5987 UTF-8 name."""
    name = sanitize_filename(filename)
    fallback = "".join(ch if " " <= ch <= "~" and ch not in '"\\%' else "_" for ch in name)
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


def _parse_metadata(raw: str | None) -> DocumentMetadata | None:
    """Validate the optional ``metadata`` form field (422 with field locations on error)."""
    if raw is None or not raw.strip():
        return None
    try:
        return DocumentMetadata.model_validate_json(raw)
    except ValidationError as exc:
        errors = [
            {"loc": ("body", "metadata", *err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
        raise RequestValidationError(errors) from None
