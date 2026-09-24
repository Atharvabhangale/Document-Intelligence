"""Composition root and FastAPI dependencies.

``build_container`` wires the application from settings. The extraction, LLM and intelligence
packages are imported inside it (not at module import), so importing the API is cheap and does
not construct clients or touch external services. The container is built once per app, on
startup or on the first request (``ContainerHolder``), unless a test injects one.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from docintel.core.config import Settings
from docintel.core.errors import DocumentNotFoundError
from docintel.core.models import DocumentRecord, Requester
from docintel.documents import DocumentService
from docintel.providers.windchill.base import WindchillDocumentProvider
from docintel.providers.windchill.factory import create_windchill_provider
from docintel.schemas.api import AIInfo
from docintel.storage.repository import (
    DocumentRepository,
    FileDocumentRepository,
    FileReportRepository,
    ReportRepository,
)

if TYPE_CHECKING:
    # Type-only: these packages load the PDF libraries and the LLM SDKs (see build_container).
    from docintel.extraction.base import TextExtractor
    from docintel.intelligence import DocumentIntelligenceService
    from docintel.providers.llm.base import LLMProvider

DEV_USER_DISPLAY_NAME = "Development User"
_DOCUMENT_ID_RE = re.compile(r"^[a-f0-9]{32}$")


@dataclass(frozen=True)
class Container:
    """Application services shared by all requests (all thread-safe)."""

    settings: Settings
    documents: DocumentRepository
    reports: ReportRepository
    extractor: TextExtractor
    windchill: WindchillDocumentProvider
    llm: LLMProvider
    intelligence: DocumentIntelligenceService
    document_service: DocumentService


def build_container(settings: Settings) -> Container:
    """Wire the application services from ``settings`` (no network calls)."""
    from docintel.extraction import get_default_extractor
    from docintel.intelligence import DocumentIntelligenceService, PromptLibrary
    from docintel.providers.llm.factory import create_llm_provider

    documents = FileDocumentRepository(settings.data_dir)
    reports = FileReportRepository(settings.data_dir)
    extractor = get_default_extractor()
    windchill = create_windchill_provider(settings)
    llm = create_llm_provider(settings)
    return Container(
        settings=settings,
        documents=documents,
        reports=reports,
        extractor=extractor,
        windchill=windchill,
        llm=llm,
        intelligence=DocumentIntelligenceService(
            llm=llm,
            reports=reports,
            prompts=PromptLibrary(settings.prompts_dir),
            settings=settings,
        ),
        document_service=DocumentService(
            repository=documents, extractor=extractor, windchill=windchill, settings=settings
        ),
    )


class ContainerHolder:
    """Builds the container lazily, exactly once (thread-safe)."""

    def __init__(self, settings: Settings, container: Container | None = None) -> None:
        self.settings = settings
        self._container = container
        self._lock = threading.Lock()

    def get(self) -> Container:
        if self._container is None:
            with self._lock:
                if self._container is None:
                    self._container = build_container(self.settings)
        return self._container


def describe_ai(llm: LLMProvider) -> AIInfo:
    """Non-secret facts about the configured LLM provider (for ``/api/health``)."""
    from docintel.providers.llm.factory import describe_provider

    description = describe_provider(llm)
    return AIInfo(
        provider=description.name,
        model=description.model,
        configured=description.configured,
        development_only=description.development_only,
    )


# --- FastAPI dependencies --------------------------------------------------------------------


def get_container(request: Request) -> Container:
    holder: ContainerHolder = request.app.state.container_holder
    return holder.get()


ContainerDep = Annotated[Container, Depends(get_container)]


def get_requester(container: ContainerDep) -> Requester:
    """The end user on whose behalf the request is made.

    DEVELOPMENT ONLY: a fixed development user. The Windchill integration must derive the
    requester from the authenticated Windchill session and never trust a client-supplied
    identity (see docs/windchill-integration.md).
    """
    return Requester(user_id=container.settings.dev_user_id, display_name=DEV_USER_DISPLAY_NAME)


RequesterDep = Annotated[Requester, Depends(get_requester)]


def get_document_record(document_id: str, container: ContainerDep) -> DocumentRecord:
    """The stored document named by the ``document_id`` path parameter.

    Malformed ids are reported exactly like unknown ones (``404 document_not_found``).
    """
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise DocumentNotFoundError()
    return container.documents.get(document_id)


DocumentRecordDep = Annotated[DocumentRecord, Depends(get_document_record)]
