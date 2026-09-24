"""Document intelligence output contracts (schema version 1.0).

There are two layers:

1. **LLM output models** (``LLM*``): what the model must return. Strict — every field is
   required (nullable where optional), no extra fields. Sources are inline ``{page, quote}``
   pairs so the pipeline can verify each quote against the extracted page text.

2. **API report models**: what the backend returns to clients. Built by the pipeline from a
   *validated* LLM output plus provider metadata, verified citations and provenance. Document
   metadata is never taken from the LLM.

The JSON Schema of the API models is exported to ``packages/schemas`` for the web client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from docintel.core.models import ApiModel, ContentFile, DocumentMetadata, DocumentSource

SCHEMA_VERSION: Literal["1.0"] = "1.0"

Basis = Literal["explicit", "inferred"]
Obligation = Literal["mandatory", "recommended", "permitted", "informational"]
Severity = Literal["high", "medium", "low"]
Priority = Literal["high", "medium", "low"]
TaskName = Literal["summarize", "requirements", "risks", "ask"]


# =============================================================================================
# 1. LLM output models
# =============================================================================================


class LLMModel(BaseModel):
    """Strict base for model-produced JSON."""

    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class SourceQuote(LLMModel):
    page: int = Field(description="1-based page number where the quote appears.")
    quote: str = Field(
        description=(
            "Short verbatim excerpt (about 5-25 words) copied exactly from that page that "
            "supports the statement."
        )
    )


class LLMExecutiveSummary(LLMModel):
    text: str = Field(description="Executive summary, 2-5 sentences, grounded in the document.")
    sources: list[SourceQuote]


class LLMKeyPoint(LLMModel):
    text: str = Field(description="One key point, one sentence.")
    sources: list[SourceQuote]


class LLMSummary(LLMModel):
    purpose: str = Field(description="One sentence stating what the document is for.")
    executive: LLMExecutiveSummary
    key_points: list[LLMKeyPoint]


class LLMRequirement(LLMModel):
    statement: str = Field(description="The requirement, preserving the document's terminology.")
    basis: Basis = Field(
        description=(
            "'explicit' if the document states it (e.g. shall/must/required); "
            "'inferred' if derived from context."
        )
    )
    obligation: Obligation = Field(
        description=(
            "mandatory (shall/must), recommended (should), permitted (may), "
            "informational (no normative wording)."
        )
    )
    category: str | None = Field(
        description="Short category such as Safety, Inspection, Documentation; null if unclear."
    )
    sources: list[SourceQuote]


class LLMSpecification(LLMModel):
    parameter: str = Field(description="The specified parameter, e.g. 'Hydraulic oil temperature'.")
    value: str = Field(description="The value or range exactly as specified, e.g. '40-60'.")
    unit: str | None = Field(description="Unit of measure, e.g. '°C'; null if none.")
    context: str | None = Field(
        description="Condition or scope in which the value applies; null if none."
    )
    sources: list[SourceQuote]


class LLMRisk(LLMModel):
    title: str = Field(description="Short title of the risk or concern.")
    description: str = Field(description="What could go wrong and why, grounded in the document.")
    severity: Severity
    basis: Basis = Field(
        description="'explicit' if the document names the hazard/concern; 'inferred' otherwise."
    )
    sources: list[SourceQuote]


class LLMAction(LLMModel):
    action: str = Field(description="A concrete recommended action for the reader.")
    rationale: str = Field(description="Why, with reference to what the document says.")
    priority: Priority
    basis: Basis = Field(
        description="'explicit' if the document directs this action; 'inferred' otherwise."
    )
    sources: list[SourceQuote]


class LLMSummarizeOutput(LLMModel):
    summary: LLMSummary
    requirements: list[LLMRequirement]
    specifications: list[LLMSpecification]
    risks: list[LLMRisk]
    actions: list[LLMAction]
    limitations: list[str] = Field(
        description=(
            "Gaps or caveats, e.g. unreadable pages, missing sections, ambiguous statements. "
            "Empty if none."
        )
    )


class LLMRequirementsOutput(LLMModel):
    requirements: list[LLMRequirement]
    limitations: list[str]


class LLMRisksOutput(LLMModel):
    risks: list[LLMRisk]
    limitations: list[str]


class LLMAnswerOutput(LLMModel):
    answerable: bool = Field(
        description="false if the document does not contain the information needed to answer."
    )
    answer: str = Field(
        description=(
            "Concise answer grounded only in the document. If not answerable, briefly say what "
            "the document does and does not cover."
        )
    )
    sources: list[SourceQuote]


# =============================================================================================
# 2. API report models
# =============================================================================================

CitationStatus = Literal["verified", "relocated", "approximate", "unverified", "invalid_page"]


class Citation(ApiModel):
    """A source reference produced by the model and checked against the extracted text.

    - ``verified``: quote found on the cited page.
    - ``relocated``: quote found, but on a different page (``matched_page``).
    - ``approximate``: close (fuzzy) match on the cited or another page.
    - ``unverified``: quote not found in the document.
    - ``invalid_page``: cited page does not exist and the quote was not found elsewhere.
    """

    id: str  # "C1", "C2", ...
    page: int  # page number as cited by the model
    quote: str
    status: CitationStatus
    matched_page: int | None = None
    match_score: float = Field(ge=0.0, le=1.0)


class ExecutiveSummary(ApiModel):
    text: str
    citation_ids: list[str]


class KeyPoint(ApiModel):
    id: str
    text: str
    citation_ids: list[str]


class SummarySection(ApiModel):
    purpose: str
    executive: ExecutiveSummary
    key_points: list[KeyPoint]


class Requirement(ApiModel):
    id: str  # "REQ-001"
    statement: str
    basis: Basis
    obligation: Obligation
    category: str | None = None
    citation_ids: list[str]


class Specification(ApiModel):
    id: str  # "SPEC-001"
    parameter: str
    value: str
    unit: str | None = None
    context: str | None = None
    citation_ids: list[str]


class Risk(ApiModel):
    id: str  # "RISK-001"
    title: str
    description: str
    severity: Severity
    basis: Basis
    citation_ids: list[str]


class RecommendedAction(ApiModel):
    id: str  # "ACT-001"
    action: str
    rationale: str
    priority: Priority
    basis: Basis
    citation_ids: list[str]


class VerificationSummary(ApiModel):
    total_citations: int
    verified: int
    relocated: int
    approximate: int
    unverified: int
    invalid_page: int
    items_total: int
    items_without_verified_source: int  # items none of whose citations is verified/relocated


class TokenUsage(ApiModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class Provenance(ApiModel):
    task: TaskName
    prompt_id: str
    prompt_version: str
    provider: str
    model: str
    pipeline_version: str
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    extractor: str
    generated_at: datetime
    duration_ms: int
    attempts: int  # 1 + number of repair attempts used
    usage: TokenUsage
    cached: bool = False  # true when this response was served from the report cache


class DocumentRef(ApiModel):
    document_id: str
    source: DocumentSource
    source_provider: str
    development_only: bool
    metadata: DocumentMetadata
    content: ContentFile
    page_count: int


class ReportBase(ApiModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    report_id: str
    document: DocumentRef
    citations: list[Citation]
    verification: VerificationSummary
    limitations: list[str]
    warnings: list[str]
    provenance: Provenance


class DocumentIntelligenceReport(ReportBase):
    task: Literal["summarize"] = "summarize"
    summary: SummarySection
    requirements: list[Requirement]
    specifications: list[Specification]
    risks: list[Risk]
    actions: list[RecommendedAction]


class RequirementsReport(ReportBase):
    task: Literal["requirements"] = "requirements"
    requirements: list[Requirement]


class RisksReport(ReportBase):
    task: Literal["risks"] = "risks"
    risks: list[Risk]


class AskRequest(ApiModel):
    question: str = Field(min_length=1)


class AskResponse(ApiModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    answer_id: str
    document_id: str
    question: str
    answerable: bool
    answer: str
    citations: list[Citation]
    verification: VerificationSummary
    warnings: list[str]
    provenance: Provenance


# =============================================================================================
# JSON Schema helpers
# =============================================================================================

_UNSUPPORTED_KEYWORDS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "default",
    "title",
}


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Inline ``$ref``s and drop unsupported keywords from a *schema node*.

    Keys of a ``properties`` mapping are property names (e.g. a property literally called
    ``title``), not keywords, so they are preserved and only their values are processed.
    """
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            name = ref.rsplit("/", 1)[-1]
            target = _inline_refs(defs[name], defs)
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return {**target, **_inline_refs(extra, defs)}
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$defs" or key in _UNSUPPORTED_KEYWORDS:
                continue
            if key == "properties" and isinstance(value, dict):
                out[key] = {name: _inline_refs(sub, defs) for name, sub in value.items()}
            else:
                out[key] = _inline_refs(value, defs)
        return out
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _force_strict_objects(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for v in node.values():
            _force_strict_objects(v)
    elif isinstance(node, list):
        for v in node:
            _force_strict_objects(v)


def llm_json_schema(model: type[LLMModel]) -> dict[str, Any]:
    """Return a provider-neutral JSON Schema for a strict LLM output model.

    The schema is fully inlined (no ``$ref``/``$defs`` — some local runtimes handle nested refs
    poorly), every object has ``additionalProperties: false`` with all properties required, and
    keywords unsupported by constrained decoding are stripped (they are enforced by Pydantic
    validation instead).
    """
    raw = model.model_json_schema(by_alias=True, mode="validation")
    defs = raw.get("$defs", {})
    schema = _inline_refs(raw, defs)
    _force_strict_objects(schema)
    return schema


def api_json_schema() -> dict[str, Any]:
    """JSON Schema bundle of the API response models (exported to packages/schemas)."""
    from pydantic.json_schema import models_json_schema

    from docintel.schemas import api as api_models

    models = [
        DocumentIntelligenceReport,
        RequirementsReport,
        RisksReport,
        AskRequest,
        AskResponse,
        api_models.ErrorResponse,
        api_models.HealthResponse,
        api_models.WindchillDocumentList,
        api_models.ImportFromWindchillRequest,
        api_models.DocumentList,
        api_models.DocumentPages,
    ]
    _, bundle = models_json_schema(
        [(m, "serialization") for m in models],
        by_alias=True,
        title="Document Intelligence API contracts",
    )
    bundle["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    bundle["$id"] = "https://docintel.local/schemas/document-intelligence.v1.schema.json"
    bundle["description"] = (
        "Generated from apps/api/src/docintel/schemas/report.py — do not edit by hand. "
        f"Schema version {SCHEMA_VERSION}."
    )
    return bundle
