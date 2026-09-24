"""Assembly of validated LLM output into API report models.

The assemblers turn a schema-valid model output into the client-facing report: stable item ids,
whitespace-normalized text, list caps, verified and deduplicated citations, verification
counts, user-safe warnings and limitations. Document metadata always comes from the
``DocumentRecord`` (the document provider), never from the model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from docintel.core.models import DocumentMetadata, DocumentRecord, ExtractedDocument
from docintel.intelligence.citations import CitationRegistry, CitationVerifier
from docintel.schemas.report import (
    AskResponse,
    CitationStatus,
    DocumentIntelligenceReport,
    DocumentRef,
    ExecutiveSummary,
    KeyPoint,
    LLMAction,
    LLMAnswerOutput,
    LLMRequirement,
    LLMRequirementsOutput,
    LLMRisk,
    LLMRisksOutput,
    LLMSpecification,
    LLMSummarizeOutput,
    LLMSummary,
    Provenance,
    RecommendedAction,
    ReportBase,
    Requirement,
    RequirementsReport,
    Risk,
    RisksReport,
    SourceQuote,
    Specification,
    SummarySection,
    VerificationSummary,
)

T = TypeVar("T")
ReportT = TypeVar("ReportT", bound=ReportBase)

KEY_POINT_LIMIT = 10
REQUIREMENT_LIMIT = 60
SPECIFICATION_LIMIT = 60
RISK_LIMIT = 30
ACTION_LIMIT = 10

#: Citation statuses that count as the document supporting an item.
SUPPORTING_STATUSES: frozenset[CitationStatus] = frozenset({"verified", "relocated"})


@dataclass(frozen=True)
class AssemblyContext:
    """Inputs an assembler needs besides the model output."""

    record: DocumentRecord
    extracted: ExtractedDocument
    result_id: str  # report id or answer id
    provenance: Provenance
    question: str | None = None  # "ask" only


# --- public helpers --------------------------------------------------------------------------


def document_ref(record: DocumentRecord) -> DocumentRef:
    """Reference to the analyzed document, built from the provider's record."""
    return DocumentRef(
        document_id=record.id,
        source=record.source,
        source_provider=record.source_provider,
        development_only=record.development_only,
        metadata=record.metadata,
        content=record.content,
        page_count=record.extraction.page_count,
    )


def record_warnings(metadata: DocumentMetadata) -> list[str]:
    """Warnings that depend on the document's business metadata (not on its content)."""
    state = (metadata.state or "").strip()
    if state and state.casefold() != "released":
        return [
            f"This document is in state '{state}', not Released. The analysis may not reflect "
            "the approved version."
        ]
    return []


def rebind_to_record(report: ReportT, record: DocumentRecord) -> ReportT:
    """Adapt a cached report to ``record``.

    Reports are cached by content, so a document with the same content as a previously analyzed
    one reuses its report. The document reference and the metadata-dependent warnings are
    re-derived from the current record; everything content-derived is kept.
    """
    stale = set(record_warnings(report.document.metadata))
    content_warnings = [warning for warning in report.warnings if warning not in stale]
    return report.model_copy(
        update={
            "document": document_ref(record),
            "warnings": _dedupe([*record_warnings(record.metadata), *content_warnings]),
        }
    )


# --- assemblers ------------------------------------------------------------------------------


def assemble_summarize(
    output: LLMSummarizeOutput, context: AssemblyContext
) -> DocumentIntelligenceReport:
    builder = _ReportBuilder(context)
    # Citation ids are assigned in reading order of the report.
    summary = _summary(builder, output.summary)
    requirements = _requirements(builder, output.requirements)
    specifications = _specifications(builder, output.specifications)
    risks = _risks(builder, output.risks)
    actions = _actions(builder, output.actions)
    return DocumentIntelligenceReport(
        report_id=context.result_id,
        document=document_ref(context.record),
        summary=summary,
        requirements=requirements,
        specifications=specifications,
        risks=risks,
        actions=actions,
        citations=builder.registry.citations,
        verification=builder.verification(),
        limitations=_clean_list(output.limitations),
        warnings=builder.warnings(),
        provenance=context.provenance,
    )


def assemble_requirements(
    output: LLMRequirementsOutput, context: AssemblyContext
) -> RequirementsReport:
    builder = _ReportBuilder(context)
    requirements = _requirements(builder, output.requirements)
    return RequirementsReport(
        report_id=context.result_id,
        document=document_ref(context.record),
        requirements=requirements,
        citations=builder.registry.citations,
        verification=builder.verification(),
        limitations=_clean_list(output.limitations),
        warnings=builder.warnings(),
        provenance=context.provenance,
    )


def assemble_risks(output: LLMRisksOutput, context: AssemblyContext) -> RisksReport:
    builder = _ReportBuilder(context)
    risks = _risks(builder, output.risks)
    return RisksReport(
        report_id=context.result_id,
        document=document_ref(context.record),
        risks=risks,
        citations=builder.registry.citations,
        verification=builder.verification(),
        limitations=_clean_list(output.limitations),
        warnings=builder.warnings(),
        provenance=context.provenance,
    )


def assemble_answer(output: LLMAnswerOutput, context: AssemblyContext) -> AskResponse:
    """Build the Q&A response.

    The answer counts as one verification item when it is answerable; an unanswerable response
    keeps whatever (closest-passage) citations the model gave but is not counted as an item.
    """
    if context.question is None:
        raise ValueError("assemble_answer requires context.question")
    builder = _ReportBuilder(context)
    builder.cite(output.sources, counted=output.answerable)
    return AskResponse(
        answer_id=context.result_id,
        document_id=context.record.id,
        question=context.question,
        answerable=output.answerable,
        answer=_clean(output.answer),
        citations=builder.registry.citations,
        verification=builder.verification(),
        warnings=builder.warnings(),
        provenance=context.provenance,
    )


# --- item lists ------------------------------------------------------------------------------


def _summary(builder: _ReportBuilder, summary: LLMSummary) -> SummarySection:
    """Purpose, executive summary (one verification item) and key points."""
    executive = ExecutiveSummary(
        text=_clean(summary.executive.text), citation_ids=builder.cite(summary.executive.sources)
    )
    selected = builder.select(
        summary.key_points,
        keep=lambda item: _has_text(item.text),
        limit=KEY_POINT_LIMIT,
        noun=("key point", "key points"),
    )
    key_points = [
        KeyPoint(
            id=f"KP-{index:02d}", text=_clean(item.text), citation_ids=builder.cite(item.sources)
        )
        for index, item in enumerate(selected, start=1)
    ]
    return SummarySection(
        purpose=_clean(summary.purpose), executive=executive, key_points=key_points
    )


def _requirements(builder: _ReportBuilder, items: Sequence[LLMRequirement]) -> list[Requirement]:
    selected = builder.select(
        items,
        keep=lambda item: _has_text(item.statement),
        limit=REQUIREMENT_LIMIT,
        noun=("requirement", "requirements"),
    )
    return [
        Requirement(
            id=f"REQ-{index:03d}",
            statement=_clean(item.statement),
            basis=item.basis,
            obligation=item.obligation,
            category=_clean_optional(item.category),
            citation_ids=builder.cite(item.sources),
        )
        for index, item in enumerate(selected, start=1)
    ]


def _specifications(
    builder: _ReportBuilder, items: Sequence[LLMSpecification]
) -> list[Specification]:
    selected = builder.select(
        items,
        keep=lambda item: _has_text(item.parameter) and _has_text(item.value),
        limit=SPECIFICATION_LIMIT,
        noun=("specification", "specifications"),
    )
    return [
        Specification(
            id=f"SPEC-{index:03d}",
            parameter=_clean(item.parameter),
            value=_clean(item.value),
            unit=_clean_optional(item.unit),
            context=_clean_optional(item.context),
            citation_ids=builder.cite(item.sources),
        )
        for index, item in enumerate(selected, start=1)
    ]


def _risks(builder: _ReportBuilder, items: Sequence[LLMRisk]) -> list[Risk]:
    selected = builder.select(
        items,
        keep=lambda item: _has_text(item.title),
        limit=RISK_LIMIT,
        noun=("risk", "risks"),
    )
    return [
        Risk(
            id=f"RISK-{index:03d}",
            title=_clean(item.title),
            description=_clean(item.description),
            severity=item.severity,
            basis=item.basis,
            citation_ids=builder.cite(item.sources),
        )
        for index, item in enumerate(selected, start=1)
    ]


def _actions(builder: _ReportBuilder, items: Sequence[LLMAction]) -> list[RecommendedAction]:
    selected = builder.select(
        items,
        keep=lambda item: _has_text(item.action),
        limit=ACTION_LIMIT,
        noun=("recommended action", "recommended actions"),
    )
    return [
        RecommendedAction(
            id=f"ACT-{index:03d}",
            action=_clean(item.action),
            rationale=_clean(item.rationale),
            priority=item.priority,
            basis=item.basis,
            citation_ids=builder.cite(item.sources),
        )
        for index, item in enumerate(selected, start=1)
    ]


# --- builder ---------------------------------------------------------------------------------


class _ReportBuilder:
    """Per-report state: citations, verification bookkeeping and list notices."""

    def __init__(self, context: AssemblyContext) -> None:
        self._context = context
        self.registry = CitationRegistry(CitationVerifier(context.extracted))
        self._items_total = 0
        self._items_unsupported = 0
        self._notices: list[str] = []

    def cite(self, sources: Iterable[SourceQuote], *, counted: bool = True) -> list[str]:
        """Register an item's sources and return its citation ids."""
        ids = self.registry.register(sources)
        if counted:
            self._items_total += 1
            if not any(self.registry.status(cid) in SUPPORTING_STATUSES for cid in ids):
                self._items_unsupported += 1
        return ids

    def select(
        self,
        items: Sequence[T],
        *,
        keep: Callable[[T], bool],
        limit: int,
        noun: tuple[str, str],
    ) -> list[T]:
        """Drop items without text and cap the list, recording a user-facing notice for each."""
        kept = [item for item in items if keep(item)]
        dropped = len(items) - len(kept)
        if dropped:
            label = noun[0] if dropped == 1 else noun[1]
            verb = "was" if dropped == 1 else "were"
            self._notices.append(f"{dropped} {label} without text {verb} omitted.")
        if len(kept) > limit:
            self._notices.append(
                f"The analysis returned {len(kept)} {noun[1]}; only the first {limit} are shown."
            )
            kept = kept[:limit]
        return kept

    def verification(self) -> VerificationSummary:
        citations = self.registry.citations

        def count(status: CitationStatus) -> int:
            return sum(1 for citation in citations if citation.status == status)

        return VerificationSummary(
            total_citations=len(citations),
            verified=count("verified"),
            relocated=count("relocated"),
            approximate=count("approximate"),
            unverified=count("unverified"),
            invalid_page=count("invalid_page"),
            items_total=self._items_total,
            items_without_verified_source=self._items_unsupported,
        )

    def warnings(self) -> list[str]:
        """User-safe warnings: document state, extraction, citation checks, list notices."""
        record, extracted = self._context.record, self._context.extracted
        warnings = [
            *record_warnings(record.metadata),
            *record.extraction.warnings,
            *extracted.warnings,
        ]
        summary = self.verification()
        failed = summary.unverified + summary.invalid_page
        if failed:
            noun = "citation" if summary.total_citations == 1 else "citations"
            warnings.append(
                f"{failed} of {summary.total_citations} {noun} could not be verified against "
                "the document text."
            )
        warnings.extend(self._notices)
        return _dedupe(warnings)


# --- text helpers ----------------------------------------------------------------------------


def _clean(text: str) -> str:
    return text.strip()


def _clean_optional(text: str | None) -> str | None:
    if text is None:
        return None
    return text.strip() or None


def _has_text(text: str) -> bool:
    return bool(text.strip())


def _clean_list(values: Iterable[str]) -> list[str]:
    """Strip, drop empty entries and remove case-insensitive duplicates (first one wins)."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = value.strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
