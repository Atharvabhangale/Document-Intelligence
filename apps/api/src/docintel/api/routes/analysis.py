"""AI analysis of a registered document.

The analysis endpoints are synchronous (``def``): FastAPI runs them in its thread pool, so a
slow model call does not block the event loop. Every result is structured JSON validated
against the report schema; model output is never rendered as HTML by the backend.

When the real Windchill provider exists, serving a report (cached or new) must be preceded by
a fresh authorization check of the requester for the document (docs/windchill-integration.md).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import Field

from docintel.api.deps import Container, ContainerDep, DocumentRecordDep
from docintel.core.errors import ReportNotFoundError
from docintel.core.models import DocumentRecord, ExtractedDocument
from docintel.schemas.report import (
    AskRequest,
    AskResponse,
    DocumentIntelligenceReport,
    RequirementsReport,
    RisksReport,
)

router = APIRouter(prefix="/api/documents", tags=["analysis"])

ReportTask = Literal["summarize", "requirements", "risks"]
AnyReport = Annotated[
    DocumentIntelligenceReport | RequirementsReport | RisksReport, Field(discriminator="task")
]
RefreshQuery = Annotated[
    bool, Query(description="Ignore a cached report and run the analysis again.")
]


@router.get("/{document_id}/reports/{task}", response_model=AnyReport)
def get_cached_report(
    task: ReportTask, record: DocumentRecordDep, container: ContainerDep
) -> DocumentIntelligenceReport | RequirementsReport | RisksReport:
    """The cached report for ``task`` under the current AI configuration, without calling the
    model. ``404 report_not_found`` if the analysis has not been run yet."""
    report = container.intelligence.cached_report(record, task)
    if report is None:
        raise ReportNotFoundError()
    return report


@router.post("/{document_id}/summarize", response_model=DocumentIntelligenceReport)
def summarize(
    record: DocumentRecordDep, container: ContainerDep, refresh: RefreshQuery = False
) -> DocumentIntelligenceReport:
    """Document intelligence report: summary, requirements, specifications, risks, actions."""
    return container.intelligence.summarize(record, _extracted(container, record), refresh=refresh)


@router.post("/{document_id}/requirements", response_model=RequirementsReport)
def extract_requirements(
    record: DocumentRecordDep, container: ContainerDep, refresh: RefreshQuery = False
) -> RequirementsReport:
    """All requirements stated in (or inferred from) the document, with citations."""
    return container.intelligence.extract_requirements(
        record, _extracted(container, record), refresh=refresh
    )


@router.post("/{document_id}/risks", response_model=RisksReport)
def identify_risks(
    record: DocumentRecordDep, container: ContainerDep, refresh: RefreshQuery = False
) -> RisksReport:
    """Risks and concerns identified in the document, with citations."""
    return container.intelligence.identify_risks(
        record, _extracted(container, record), refresh=refresh
    )


@router.post("/{document_id}/ask", response_model=AskResponse)
def ask(body: AskRequest, record: DocumentRecordDep, container: ContainerDep) -> AskResponse:
    """Answer a question using only the document, with citations (not cached)."""
    return container.intelligence.ask(record, _extracted(container, record), body.question)


def _extracted(container: Container, record: DocumentRecord) -> ExtractedDocument:
    return container.documents.get_extracted(record.id)
