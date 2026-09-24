"""Windchill document provider abstraction.

This is the boundary between the intelligence service and the document source. The rest of the
backend never talks to Windchill directly.

Implementations:

* ``MockWindchillDocumentProvider`` — DEVELOPMENT ONLY. Serves a small catalog of realistic,
  locally generated SOP PDFs. It is not connected to Windchill.
* ``Windchill12DocumentProvider`` — placeholder for Windchill 12.0.2.19 via Windchill REST
  Services. Not implemented: the exact WRS endpoints must be validated against the target
  system before any code is written (see docs/windchill-integration.md).

Security contract (MUST hold for every real implementation):

* Every call is made on behalf of ``requester``. A real provider must ensure the requester is
  authorized to read the document AND download its content (Windchill distinguishes the Read
  and Download permissions). The confirmed deployment uses an integration/service account for
  WRS, which can see more than an individual user — so per-user authorization must be enforced
  explicitly before content is returned. Never return content the requester could not
  download in Windchill.
* Raise ``DocumentNotFoundError`` for unknown references, ``AccessDeniedError`` when the
  requester is not authorized, ``ContentNotAvailableError`` when there is no supported primary
  content, and ``WindchillProviderError`` for transport failures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from docintel.core.models import ApiModel, DocumentMetadata, Requester


class ContentDescriptor(ApiModel):
    filename: str
    media_type: str
    size_bytes: int | None = None


class WindchillDocument(ApiModel):
    """A document as described by the provider (metadata only, no content bytes)."""

    reference: str  # opaque, provider-specific reference used to fetch the document
    metadata: DocumentMetadata
    primary_content: ContentDescriptor | None = None
    development_only: bool


@dataclass(frozen=True)
class DocumentContent:
    filename: str
    media_type: str
    data: bytes
    role: str = "primary"


class WindchillDocumentProvider(ABC):
    #: Provider id, e.g. "mock-windchill", "windchill12".
    name: str
    #: True when data is not from a real Windchill system. Must be surfaced in the UI.
    development_only: bool

    @abstractmethod
    def list_documents(
        self, *, requester: Requester, query: str | None = None, limit: int = 50
    ) -> list[WindchillDocument]:
        """List/search documents visible to ``requester`` (used for development browsing)."""

    @abstractmethod
    def get_document(self, reference: str, *, requester: Requester) -> WindchillDocument:
        """Return metadata for ``reference``."""

    @abstractmethod
    def get_primary_content(self, reference: str, *, requester: Requester) -> DocumentContent:
        """Return the primary content (bytes) of ``reference``."""
