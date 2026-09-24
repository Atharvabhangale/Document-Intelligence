"""Document intelligence pipeline: prompts, document context, LLM output validation, citation
verification, report assembly, caching and the service used by the API."""

from docintel.intelligence.citations import (
    CitationMatch,
    CitationRegistry,
    CitationVerifier,
)
from docintel.intelligence.context import (
    build_document_context,
    ensure_analyzable,
    estimate_tokens,
)
from docintel.intelligence.parsing import OutputValidationFailure, parse_llm_output
from docintel.intelligence.prompts import PromptLibrary, PromptTemplate
from docintel.intelligence.service import (
    PIPELINE_VERSION,
    DocumentIntelligenceService,
    report_cache_key,
)
from docintel.intelligence.tasks import TASKS, ReportTaskName, TaskSpec, get_task

__all__ = [
    "PIPELINE_VERSION",
    "TASKS",
    "CitationMatch",
    "CitationRegistry",
    "CitationVerifier",
    "DocumentIntelligenceService",
    "OutputValidationFailure",
    "PromptLibrary",
    "PromptTemplate",
    "ReportTaskName",
    "TaskSpec",
    "build_document_context",
    "ensure_analyzable",
    "estimate_tokens",
    "get_task",
    "parse_llm_output",
    "report_cache_key",
]
