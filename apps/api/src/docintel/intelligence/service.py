"""Document intelligence service: the pipeline the API calls.

For a report task (summarize, requirements, risks)::

    guard (text present, size within limit)
      -> report cache lookup (unless refresh)
      -> LLM request (system prompt + page-tagged document + task instruction + JSON schema)
      -> finish-reason checks (truncation, refusal)
      -> parse + validate, with bounded repair attempts on invalid output
      -> assembly (ids, verified citations, warnings) + provenance
      -> persist to the report cache

Q&A (``ask``) follows the same flow without caching.

The service holds no mutable state of its own (the report repository is the only shared state),
so one instance can serve concurrent requests. Logs contain identifiers, counts and timings
only, never prompts, document text or model output.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import ValidationError

from docintel.core.config import Settings
from docintel.core.errors import (
    AIOutputTruncatedError,
    AIOutputValidationError,
    AIRefusalError,
    InvalidRequestError,
)
from docintel.core.models import DocumentRecord, ExtractedDocument
from docintel.intelligence.assemble import AssemblyContext, rebind_to_record
from docintel.intelligence.context import (
    build_document_context,
    ensure_analyzable,
    neutralize_tags,
)
from docintel.intelligence.parsing import OutputValidationFailure, parse_llm_output
from docintel.intelligence.prompts import PromptLibrary, PromptTemplate
from docintel.intelligence.tasks import (
    ASK,
    REQUIREMENTS,
    RISKS,
    SUMMARIZE,
    TASKS,
    OutputT,
    ReportTaskName,
    TaskSpec,
)
from docintel.providers.llm.base import LLMProvider, LLMRequest, LLMUsage
from docintel.schemas.report import (
    SCHEMA_VERSION,
    AskResponse,
    DocumentIntelligenceReport,
    Provenance,
    ReportBase,
    RequirementsReport,
    RisksReport,
    TokenUsage,
    VerificationSummary,
    llm_json_schema,
)
from docintel.storage.repository import ReportRepository

PIPELINE_VERSION = "1.0.0"

REPAIR_INSTRUCTION = (
    "\n\nYour previous response was rejected because it did not match the required JSON "
    "schema:\n{problems}\n"
    "Return a complete, corrected JSON response that matches the schema exactly."
)

logger = logging.getLogger(__name__)

ReportT = TypeVar("ReportT", bound=ReportBase)
AnyReport = DocumentIntelligenceReport | RequirementsReport | RisksReport

# Tag-like sequences neutralized inside the user's question so it cannot close its container.
_QUESTION_TAG_RE = re.compile(r"<(?=\s*/?\s*(?:question|page|document))", re.IGNORECASE)


@dataclass(frozen=True)
class _Generation(Generic[OutputT]):
    output: OutputT
    attempts: int
    usage: TokenUsage
    model: str


def report_cache_key(
    record: DocumentRecord, task: str, prompt: PromptTemplate, llm: LLMProvider
) -> str:
    """Cache key of a report: content, task, prompt version, provider/model and pipeline."""
    parts = [
        record.content.sha256,
        task,
        f"{prompt.id}@{prompt.version}",
        llm.name,
        llm.model,
        PIPELINE_VERSION,
        SCHEMA_VERSION,
        record.extraction.extractor,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class DocumentIntelligenceService:
    """Runs intelligence tasks for one configured LLM provider (thread-safe)."""

    def __init__(
        self,
        *,
        llm: LLMProvider,
        reports: ReportRepository,
        prompts: PromptLibrary,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._reports = reports
        self._prompts = prompts
        self._settings = settings

    # --- public API --------------------------------------------------------------------------

    def summarize(
        self, record: DocumentRecord, extracted: ExtractedDocument, *, refresh: bool = False
    ) -> DocumentIntelligenceReport:
        """Structured document intelligence report (cached per content and configuration)."""
        return self._run_report(SUMMARIZE, record, extracted, refresh=refresh)

    def extract_requirements(
        self, record: DocumentRecord, extracted: ExtractedDocument, *, refresh: bool = False
    ) -> RequirementsReport:
        """Exhaustive requirements extraction (cached)."""
        return self._run_report(REQUIREMENTS, record, extracted, refresh=refresh)

    def identify_risks(
        self, record: DocumentRecord, extracted: ExtractedDocument, *, refresh: bool = False
    ) -> RisksReport:
        """Risks and concerns (cached)."""
        return self._run_report(RISKS, record, extracted, refresh=refresh)

    def ask(
        self, record: DocumentRecord, extracted: ExtractedDocument, question: str
    ) -> AskResponse:
        """Answer a question grounded in the document (not cached).

        Raises:
            InvalidRequestError: the question is empty or too long.
        """
        question = self._validate_question(question)
        started = time.perf_counter()
        prompt = self._prompts.get(ASK.prompt_id)
        context = self._document_context(record, extracted)
        instruction = (
            f"{prompt.instruction}\n\n<question>\n"
            f"{neutralize_tags(question, _QUESTION_TAG_RE)}\n</question>"
        )
        generation = self._generate(ASK, prompt, context, instruction, document_id=record.id)
        response = ASK.assembler(
            generation.output,
            AssemblyContext(
                record=record,
                extracted=extracted,
                result_id=uuid4().hex,
                provenance=self._provenance(ASK, prompt, extracted, generation, started),
                question=question,
            ),
        )
        self._log_run(ASK, record, response.provenance, response.verification)
        return response

    def cached_report(self, record: DocumentRecord, task: ReportTaskName) -> AnyReport | None:
        """The cached report for ``task`` under the current configuration, if any.

        This is what ``summarize`` / ``extract_requirements`` / ``identify_risks`` would return
        without calling the model (same cache key: content, prompt version, provider, model,
        pipeline and schema version). Returns ``None`` when there is none or it is invalid.

        Raises:
            InvalidRequestError: ``task`` is not a report task.
        """
        spec = TASKS.get(task)
        if spec is None or not spec.cacheable:
            raise InvalidRequestError("Unknown analysis task.")
        prompt = self._prompts.get(spec.prompt_id)
        return self._cached(spec, record, report_cache_key(record, spec.name, prompt, self._llm))

    # --- pipeline ----------------------------------------------------------------------------

    def _run_report(
        self,
        spec: TaskSpec[Any, ReportT],
        record: DocumentRecord,
        extracted: ExtractedDocument,
        *,
        refresh: bool,
    ) -> ReportT:
        started = time.perf_counter()
        prompt = self._prompts.get(spec.prompt_id)
        context = self._document_context(record, extracted)
        key = report_cache_key(record, spec.name, prompt, self._llm)
        if not refresh:
            cached = self._cached(spec, record, key)
            if cached is not None:
                logger.info(
                    "intelligence task served from cache: task=%s document=%s provider=%s model=%s",
                    spec.name,
                    record.id,
                    self._llm.name,
                    self._llm.model,
                )
                return cached

        generation = self._generate(
            spec, prompt, context, prompt.instruction, document_id=record.id
        )
        report = spec.assembler(
            generation.output,
            AssemblyContext(
                record=record,
                extracted=extracted,
                result_id=uuid4().hex,
                provenance=self._provenance(spec, prompt, extracted, generation, started),
            ),
        )
        self._store(key, record, spec, report)
        self._log_run(spec, record, report.provenance, report.verification)
        return report

    def _document_context(self, record: DocumentRecord, extracted: ExtractedDocument) -> str:
        """Build the document context and apply the no-text / size guards."""
        context = build_document_context(record.metadata, extracted)
        ensure_analyzable(
            extracted, context, max_document_tokens=self._settings.max_document_tokens
        )
        return context

    def _generate(
        self,
        spec: TaskSpec[OutputT, Any],
        prompt: PromptTemplate,
        context: str,
        instruction: str,
        *,
        document_id: str,
    ) -> _Generation[OutputT]:
        """Call the model and validate its output.

        Invalid output is sent back for repair up to ``ai_max_repair_attempts`` times, each time
        with the original instruction plus the latest problem list. Provider errors propagate
        unchanged.
        """
        schema = llm_json_schema(spec.output_model)
        max_attempts = 1 + self._settings.ai_max_repair_attempts
        usage: list[LLMUsage] = []
        request_instruction = instruction
        for attempt in range(1, max_attempts + 1):
            response = self._llm.generate_json(
                LLMRequest(
                    system=prompt.system,
                    document_context=context,
                    instruction=request_instruction,
                    json_schema=schema,
                    schema_name=spec.name,
                    max_output_tokens=self._settings.ai_max_output_tokens,
                    temperature=self._settings.ai_temperature,
                )
            )
            usage.append(response.usage)
            if response.finish_reason == "max_tokens":
                logger.warning(
                    "LLM output truncated: task=%s document=%s attempt=%d output_tokens=%s",
                    spec.name,
                    document_id,
                    attempt,
                    response.usage.output_tokens,
                )
                raise AIOutputTruncatedError()
            if response.finish_reason == "refusal":
                logger.warning(
                    "LLM refused: task=%s document=%s attempt=%d", spec.name, document_id, attempt
                )
                raise AIRefusalError()
            try:
                output = parse_llm_output(response.text, spec.output_model)
            except OutputValidationFailure as failure:
                logger.warning(
                    "LLM output rejected: task=%s document=%s attempt=%d/%d kind=%s "
                    "problems=%d paths=%r",
                    spec.name,
                    document_id,
                    attempt,
                    max_attempts,
                    failure.kind,
                    failure.total,
                    failure.paths[:10],
                )
                request_instruction = instruction + REPAIR_INSTRUCTION.format(
                    problems=failure.feedback()
                )
                continue
            return _Generation(
                output=output,
                attempts=attempt,
                usage=_sum_usage(usage),
                model=response.model or self._llm.model,
            )
        logger.error(
            "LLM output invalid after all attempts: task=%s document=%s attempts=%d",
            spec.name,
            document_id,
            max_attempts,
        )
        raise AIOutputValidationError(details={"attempts": max_attempts})

    def _provenance(
        self,
        spec: TaskSpec[Any, Any],
        prompt: PromptTemplate,
        extracted: ExtractedDocument,
        generation: _Generation[Any],
        started: float,
    ) -> Provenance:
        return Provenance(
            task=spec.name,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            provider=self._llm.name,
            model=generation.model,
            pipeline_version=PIPELINE_VERSION,
            extractor=extracted.extractor,
            generated_at=datetime.now(UTC),
            duration_ms=round((time.perf_counter() - started) * 1000),
            attempts=generation.attempts,
            usage=generation.usage,
            cached=False,
        )

    # --- cache -------------------------------------------------------------------------------

    def _cached(
        self, spec: TaskSpec[Any, ReportT], record: DocumentRecord, key: str
    ) -> ReportT | None:
        data = self._reports.get(key)
        if data is None:
            return None
        try:
            report = spec.result_model.model_validate(data)
        except ValidationError as exc:
            logger.warning(
                "Ignoring invalid cached report: task=%s document=%s errors=%d",
                spec.name,
                record.id,
                exc.error_count(),
            )
            return None
        report = rebind_to_record(report, record)
        provenance = report.provenance.model_copy(update={"cached": True})
        return report.model_copy(update={"provenance": provenance})

    def _store(
        self, key: str, record: DocumentRecord, spec: TaskSpec[Any, Any], report: ReportBase
    ) -> None:
        try:
            self._reports.put(
                key, record.id, spec.name, report.model_dump(mode="json", by_alias=True)
            )
        except OSError as exc:
            # The analysis itself succeeded; failing to cache it must not lose the result.
            logger.warning(
                "Could not store report: task=%s document=%s error=%s",
                spec.name,
                record.id,
                type(exc).__name__,
            )

    # --- helpers -----------------------------------------------------------------------------

    def _validate_question(self, question: str) -> str:
        text = question.strip() if isinstance(question, str) else ""
        if not text:
            raise InvalidRequestError("Please enter a question.")
        limit = self._settings.max_question_chars
        if len(text) > limit:
            raise InvalidRequestError(
                f"The question is too long (at most {limit:,} characters).",
                details={"maxQuestionChars": limit},
            )
        return text

    def _log_run(
        self,
        spec: TaskSpec[Any, Any],
        record: DocumentRecord,
        provenance: Provenance,
        verification: VerificationSummary,
    ) -> None:
        logger.info(
            "intelligence task completed: task=%s document=%s provider=%s model=%s attempts=%d "
            "duration_ms=%d input_tokens=%s output_tokens=%s cache_read_tokens=%s "
            "citations=%d verified=%d relocated=%d approximate=%d unverified=%d "
            "invalid_page=%d items=%d items_without_verified_source=%d",
            spec.name,
            record.id,
            provenance.provider,
            provenance.model,
            provenance.attempts,
            provenance.duration_ms,
            provenance.usage.input_tokens,
            provenance.usage.output_tokens,
            provenance.usage.cache_read_input_tokens,
            verification.total_citations,
            verification.verified,
            verification.relocated,
            verification.approximate,
            verification.unverified,
            verification.invalid_page,
            verification.items_total,
            verification.items_without_verified_source,
        )


def _sum_usage(usages: list[LLMUsage]) -> TokenUsage:
    """Sum token usage over attempts; a field stays ``None`` if no attempt reported it."""

    def total(values: list[int | None]) -> int | None:
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    return TokenUsage(
        input_tokens=total([u.input_tokens for u in usages]),
        output_tokens=total([u.output_tokens for u in usages]),
        cache_read_input_tokens=total([u.cache_read_input_tokens for u in usages]),
    )
