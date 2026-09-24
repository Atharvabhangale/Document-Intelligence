"""Windchill 12 document provider (stub, not implemented).

Target system:

* PTC Windchill 12.0.2.19, Windchill REST Services (WRS) enabled.
* An integration/service account that is confirmed to be able to call the Document Management
  REST APIs and download document content.

Nothing in this module assumes a concrete WRS endpoint, URL, query syntax or payload shape.
Those must be read from the target server and recorded in ``docs/windchill-integration.md``
before any code is written. Background: ``WINDCHILL_AI_RESEARCH.md`` (sections 3, 4, 6, 8, 9).

To VALIDATE on the target system before implementing each method:

1. Document lookup by reference: the reference format passed by the Windchill action, and how
   it resolves to a WTDocument version/iteration (including "latest iteration" semantics).
2. Metadata: number, name, revision, iteration, lifecycle state (e.g. Released), library /
   folder location, document type, modified date and modifier, mapped to
   ``DocumentMetadata``.
3. Primary content download: how the primary content (PDF) is located and downloaded, which
   authentication applies, redirects, timeouts and size limits; and how to handle documents
   whose PDF is an attachment or a published representation.
4. Per-user authorization of the requester. The service account can see more than the end
   user, so before returning metadata or content the provider MUST verify that the
   ``requester`` has Read permission AND Download permission on that document iteration in
   Windchill, and raise ``AccessDeniedError`` otherwise. Negative tests are required (a user
   with Read but not Download, and a user with no access).

Until then every method raises ``WindchillNotImplementedError`` (HTTP 501).
"""

from __future__ import annotations

from docintel.core.errors import WindchillNotImplementedError
from docintel.core.models import Requester
from docintel.providers.windchill.base import (
    DocumentContent,
    WindchillDocument,
    WindchillDocumentProvider,
)


class Windchill12DocumentProvider(WindchillDocumentProvider):
    """Placeholder for the real Windchill 12.0.2.19 integration (see module docstring)."""

    name = "windchill12"
    development_only = False

    def list_documents(
        self, *, requester: Requester, query: str | None = None, limit: int = 50
    ) -> list[WindchillDocument]:
        raise WindchillNotImplementedError()

    def get_document(self, reference: str, *, requester: Requester) -> WindchillDocument:
        raise WindchillNotImplementedError()

    def get_primary_content(self, reference: str, *, requester: Requester) -> DocumentContent:
        raise WindchillNotImplementedError()
