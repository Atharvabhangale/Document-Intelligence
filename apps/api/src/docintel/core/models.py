"""Core domain models shared across the backend.

JSON field names are camelCase on the wire (for the web client); Python attributes are
snake_case. Construct models with either form (``populate_by_name=True``).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for all API-facing models (camelCase JSON, snake_case Python)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


# --- Documents ------------------------------------------------------------------------------


class DocumentSource(StrEnum):
    WINDCHILL = "windchill"
    UPLOAD = "upload"


class DocumentMetadata(ApiModel):
    """Business metadata of a document (Windchill-like for WTDocuments).

    Comes from the document provider — NEVER from the LLM.
    """

    number: str | None = None
    name: str
    revision: str | None = None
    iteration: str | None = None
    state: str | None = None
    location: str | None = None  # e.g. "Library / Maintenance"
    document_type: str | None = None  # e.g. "SOP"
    modified_date: datetime | None = None
    modified_by: str | None = None
    # Opaque identifier of the object in its source system (e.g. a Windchill object reference).
    source_ref: str | None = None

    @property
    def version_label(self) -> str | None:
        """Windchill-style "A.3" label when revision and iteration are known."""
        if self.revision and self.iteration:
            return f"{self.revision}.{self.iteration}"
        return self.revision


class ContentFile(ApiModel):
    filename: str
    media_type: str = "application/pdf"
    size_bytes: int = Field(ge=0)
    sha256: str
    role: str = "primary"  # "primary" | "attachment" | "upload"


class ExtractedPage(ApiModel):
    number: int = Field(ge=1)  # 1-based physical page number
    text: str
    char_count: int = Field(ge=0)
    has_text_layer: bool
    needs_ocr: bool  # true when the page appears to be an image without a usable text layer


class ExtractedDocument(ApiModel):
    page_count: int = Field(ge=0)
    pages: list[ExtractedPage]
    extractor: str  # e.g. "pdfplumber 0.11.10"
    warnings: list[str] = Field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(p.char_count for p in self.pages)

    @property
    def pages_with_text(self) -> int:
        return sum(1 for p in self.pages if p.char_count > 0)

    @property
    def pages_needing_ocr(self) -> list[int]:
        return [p.number for p in self.pages if p.needs_ocr]


class ExtractionSummary(ApiModel):
    page_count: int
    pages_with_text: int
    pages_needing_ocr: list[int]
    total_chars: int
    extractor: str
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_extracted(cls, doc: ExtractedDocument) -> ExtractionSummary:
        return cls(
            page_count=doc.page_count,
            pages_with_text=doc.pages_with_text,
            pages_needing_ocr=doc.pages_needing_ocr,
            total_chars=doc.total_chars,
            extractor=doc.extractor,
            warnings=list(doc.warnings),
        )


class DocumentRecord(ApiModel):
    """A document registered with the intelligence service (uploaded or loaded from a provider)."""

    id: str
    source: DocumentSource
    source_provider: str  # e.g. "mock-windchill", "upload"
    development_only: bool  # true for mock/dev sources — must be surfaced in the UI
    metadata: DocumentMetadata
    content: ContentFile
    extraction: ExtractionSummary
    created_at: datetime


class Requester(ApiModel):
    """The end user on whose behalf a request is made.

    In development this is a fixed dev user. In the Windchill integration it must be derived
    from the authenticated Windchill session, and every content access must be authorized for
    this user (see docs/windchill-integration.md).
    """

    user_id: str
    display_name: str | None = None
