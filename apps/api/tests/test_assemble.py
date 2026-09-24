"""Assembly of validated LLM output into API reports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from conftest import make_extracted, make_record
from docintel.core.models import ExtractedDocument, ExtractedPage, ExtractionSummary
from docintel.intelligence.assemble import (
    ACTION_LIMIT,
    KEY_POINT_LIMIT,
    REQUIREMENT_LIMIT,
    RISK_LIMIT,
    SPECIFICATION_LIMIT,
    AssemblyContext,
    assemble_answer,
    assemble_requirements,
    assemble_risks,
    assemble_summarize,
    document_ref,
    rebind_to_record,
    record_warnings,
)
from docintel.schemas.report import (
    LLMAnswerOutput,
    LLMRequirementsOutput,
    LLMRisksOutput,
    LLMSummarizeOutput,
    Provenance,
    TokenUsage,
)

PAGES = [
    "1. Purpose\nThis procedure defines the preventive maintenance of the hydraulic press HP-200.",
    "2. Safety\nWARNING: Lock out and tag out the main power supply before opening the guard.\n"
    "Operators must wear safety glasses and gloves at all times.",
    "3. Procedure\nCheck the hydraulic oil level daily. The oil temperature must stay between "
    "40-60 \u00b0C.\nTorque the pump flange bolts to 45 Nm.",
]

Q_PURPOSE = {"page": 1, "quote": "defines the preventive maintenance of the hydraulic press"}
Q_LOTO = {"page": 2, "quote": "Lock out and tag out the main power supply"}
Q_GLASSES = {"page": 2, "quote": "Operators must wear safety glasses and gloves"}
Q_TEMP = {"page": 3, "quote": "The oil temperature must stay between 40-60 \u00b0C"}
Q_TORQUE_WRONG_PAGE = {"page": 1, "quote": "Torque the pump flange bolts to 45 Nm"}  # relocated
Q_APPROX = {"page": 3, "quote": "Check the hydraulic oil level every day. The oil temperature must"}
Q_INVENTED = {"page": 3, "quote": "Replace the conveyor belt every twelve months using kit 55"}
Q_BAD_PAGE = {"page": 9, "quote": "Calibrate the pressure sensor with the reference gauge"}


def _requirement(statement: str = "Lock out the power supply.", **kw: Any) -> dict[str, Any]:
    return {
        "statement": statement,
        "basis": "explicit",
        "obligation": "mandatory",
        "category": "Safety",
        "sources": [Q_LOTO],
        **kw,
    }


def _specification(parameter: str = "Oil temperature", **kw: Any) -> dict[str, Any]:
    return {
        "parameter": parameter,
        "value": "40-60",
        "unit": "\u00b0C",
        "context": None,
        "sources": [Q_TEMP],
        **kw,
    }


def _risk(title: str = "Electrical hazard", **kw: Any) -> dict[str, Any]:
    return {
        "title": title,
        "description": "Opening the guard while energized.",
        "severity": "high",
        "basis": "explicit",
        "sources": [Q_LOTO],
        **kw,
    }


def _action(action: str = "Confirm LOTO training.", **kw: Any) -> dict[str, Any]:
    return {
        "action": action,
        "rationale": "The procedure requires lockout.",
        "priority": "high",
        "basis": "inferred",
        "sources": [Q_LOTO],
        **kw,
    }


def _summarize_output(**overrides: Any) -> LLMSummarizeOutput:
    data: dict[str, Any] = {
        "summary": {
            "purpose": "  Defines preventive maintenance of press HP-200.  ",
            "executive": {"text": " The SOP covers maintenance. ", "sources": [Q_PURPOSE]},
            "keyPoints": [
                {"text": "Lockout is mandatory.", "sources": [Q_LOTO]},
                {"text": "PPE is required.", "sources": [Q_GLASSES]},
            ],
        },
        "requirements": [_requirement(), _requirement("Wear safety glasses.", sources=[Q_GLASSES])],
        "specifications": [_specification()],
        "risks": [_risk()],
        "actions": [_action()],
        "limitations": [],
    }
    data.update(overrides)
    return LLMSummarizeOutput.model_validate(data)


def _provenance(task: str = "summarize") -> Provenance:
    return Provenance(
        task=task,  # type: ignore[arg-type]
        prompt_id=task,
        prompt_version="1",
        provider="scripted",
        model="scripted-model",
        pipeline_version="1.0.0",
        extractor="test-extractor 1.0",
        generated_at=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        duration_ms=5,
        attempts=1,
        usage=TokenUsage(input_tokens=100, output_tokens=50),
    )


def _context(
    extracted: ExtractedDocument | None = None,
    *,
    state: str | None = "Released",
    task: str = "summarize",
    question: str | None = None,
) -> AssemblyContext:
    extracted = extracted or make_extracted(PAGES)
    return AssemblyContext(
        record=make_record(extracted, state=state),
        extracted=extracted,
        result_id="r" * 32,
        provenance=_provenance(task),
        question=question,
    )


# --- summarize ---------------------------------------------------------------------------------


def test_summarize_report_structure_and_ids() -> None:
    context = _context()
    output = _summarize_output(
        requirements=[_requirement(f"Requirement {i}.") for i in range(3)],
        specifications=[_specification(f"Parameter {i}") for i in range(2)],
        risks=[_risk(f"Risk {i}") for i in range(2)],
        actions=[_action(f"Action {i}") for i in range(2)],
    )

    report = assemble_summarize(output, context)

    assert report.task == "summarize"
    assert report.report_id == context.result_id
    assert report.provenance == context.provenance
    assert [kp.id for kp in report.summary.key_points] == ["KP-01", "KP-02"]
    assert [r.id for r in report.requirements] == ["REQ-001", "REQ-002", "REQ-003"]
    assert [s.id for s in report.specifications] == ["SPEC-001", "SPEC-002"]
    assert [r.id for r in report.risks] == ["RISK-001", "RISK-002"]
    assert [a.id for a in report.actions] == ["ACT-001", "ACT-002"]
    assert report.warnings == []
    assert report.limitations == []


def test_text_is_stripped_and_blank_optionals_become_none() -> None:
    output = _summarize_output(
        requirements=[_requirement("  Wear gloves.  ", category="   ")],
        specifications=[_specification("  Torque ", value=" 45 ", unit=" ", context="  ")],
    )

    report = assemble_summarize(output, _context())

    assert report.summary.purpose == "Defines preventive maintenance of press HP-200."
    assert report.summary.executive.text == "The SOP covers maintenance."
    assert report.requirements[0].statement == "Wear gloves."
    assert report.requirements[0].category is None
    spec = report.specifications[0]
    assert (spec.parameter, spec.value, spec.unit, spec.context) == ("Torque", "45", None, None)


def test_citations_are_registered_in_reading_order_and_deduplicated() -> None:
    report = assemble_summarize(_summarize_output(), _context())

    # executive (purpose quote), KP-01 (LOTO), KP-02 (glasses); later items reuse them; the
    # specification adds the temperature quote.
    assert [c.id for c in report.citations] == ["C1", "C2", "C3", "C4"]
    assert report.summary.executive.citation_ids == ["C1"]
    assert report.summary.key_points[0].citation_ids == ["C2"]
    assert report.requirements[0].citation_ids == ["C2"]
    assert report.requirements[1].citation_ids == ["C3"]
    assert report.specifications[0].citation_ids == ["C4"]
    assert report.risks[0].citation_ids == ["C2"]
    assert report.actions[0].citation_ids == ["C2"]
    assert all(c.status == "verified" for c in report.citations)


def test_verification_summary_math() -> None:
    output = _summarize_output(
        summary={
            "purpose": "p",
            "executive": {"text": "e", "sources": [Q_PURPOSE]},  # verified
            "keyPoints": [
                {"text": "relocated only", "sources": [Q_TORQUE_WRONG_PAGE]},  # supported
                {"text": "approximate only", "sources": [Q_APPROX]},  # not supported
                {"text": "no sources", "sources": []},  # not supported
            ],
        },
        requirements=[
            _requirement(sources=[Q_INVENTED, Q_GLASSES]),  # supported (one verified)
            _requirement("r2", sources=[Q_BAD_PAGE]),  # not supported
        ],
        specifications=[_specification(sources=[Q_INVENTED])],  # not supported (dup citation)
        risks=[],
        actions=[],
    )

    report = assemble_summarize(output, _context())
    statuses = {c.quote: c.status for c in report.citations}
    summary = report.verification

    assert statuses[Q_PURPOSE["quote"]] == "verified"
    assert statuses[Q_TORQUE_WRONG_PAGE["quote"]] == "relocated"
    assert statuses[Q_APPROX["quote"]] == "approximate"
    assert statuses[Q_INVENTED["quote"]] == "unverified"
    assert statuses[Q_BAD_PAGE["quote"]] == "invalid_page"
    assert summary.total_citations == 6
    assert (summary.verified, summary.relocated, summary.approximate) == (2, 1, 1)
    assert (summary.unverified, summary.invalid_page) == (1, 1)
    # 1 executive summary + 3 key points + 2 requirements + 1 specification
    assert summary.items_total == 7
    assert summary.items_without_verified_source == 4
    assert "2 of 6 citations could not be verified against the document text." in report.warnings


def test_relocated_citation_reports_matched_page() -> None:
    output = _summarize_output(specifications=[_specification(sources=[Q_TORQUE_WRONG_PAGE])])

    citation = next(
        c for c in assemble_summarize(output, _context()).citations if c.status == "relocated"
    )

    assert citation.page == 1
    assert citation.matched_page == 3


@pytest.mark.parametrize(
    ("field", "limit", "factory", "label"),
    [
        ("requirements", REQUIREMENT_LIMIT, _requirement, "requirements"),
        ("specifications", SPECIFICATION_LIMIT, _specification, "specifications"),
        ("risks", RISK_LIMIT, _risk, "risks"),
        ("actions", ACTION_LIMIT, _action, "recommended actions"),
    ],
)
def test_lists_are_capped_with_a_warning(field: str, limit: int, factory: Any, label: str) -> None:
    items = [factory(f"Item {i}") for i in range(limit + 5)]

    report = assemble_summarize(_summarize_output(**{field: items}), _context())
    kept = getattr(report, field)

    assert len(kept) == limit
    assert kept[-1].id.endswith(f"{limit:03d}")
    assert (
        f"The analysis returned {limit + 5} {label}; only the first {limit} are shown."
        in report.warnings
    )


def test_key_points_are_capped_with_a_warning() -> None:
    points = [{"text": f"Point {i}", "sources": [Q_LOTO]} for i in range(KEY_POINT_LIMIT + 2)]
    output = _summarize_output(
        summary={
            "purpose": "p",
            "executive": {"text": "e", "sources": []},
            "keyPoints": points,
        }
    )

    report = assemble_summarize(output, _context())

    assert len(report.summary.key_points) == KEY_POINT_LIMIT
    assert report.summary.key_points[-1].id == "KP-10"
    assert (
        f"The analysis returned {KEY_POINT_LIMIT + 2} key points; only the first "
        f"{KEY_POINT_LIMIT} are shown." in report.warnings
    )


def test_items_without_text_are_dropped_with_a_warning() -> None:
    output = _summarize_output(
        summary={
            "purpose": "p",
            "executive": {"text": "e", "sources": [Q_PURPOSE]},
            "keyPoints": [
                {"text": "  ", "sources": [Q_LOTO]},
                {"text": "Kept point", "sources": [Q_GLASSES]},
            ],
        },
        requirements=[_requirement(" "), _requirement("Kept"), _requirement("")],
        specifications=[_specification(value="  "), _specification("Kept")],
        risks=[_risk("")],
        actions=[_action("\n")],
    )

    report = assemble_summarize(output, _context())

    assert [(kp.id, kp.text) for kp in report.summary.key_points] == [("KP-01", "Kept point")]
    assert [(r.id, r.statement) for r in report.requirements] == [("REQ-001", "Kept")]
    assert [s.parameter for s in report.specifications] == ["Kept"]
    assert report.risks == [] and report.actions == []
    assert "1 key point without text was omitted." in report.warnings
    assert "2 requirements without text were omitted." in report.warnings
    assert "1 specification without text was omitted." in report.warnings
    assert "1 risk without text was omitted." in report.warnings
    assert "1 recommended action without text was omitted." in report.warnings
    # Sources of dropped items are not registered.
    assert report.verification.items_total == 1 + 1 + 1 + 1
    assert [c.quote for c in report.citations].count(Q_LOTO["quote"]) == 1


def test_limitations_are_cleaned() -> None:
    output = _summarize_output(
        limitations=["  Page 4 is unreadable. ", "", "page 4 is unreadable.", "Annex B missing."]
    )

    report = assemble_summarize(output, _context())

    assert report.limitations == ["Page 4 is unreadable.", "Annex B missing."]


# --- document reference and warnings -----------------------------------------------------------


def test_document_metadata_comes_from_the_record() -> None:
    context = _context()

    report = assemble_summarize(_summarize_output(), context)

    assert report.document == document_ref(context.record)
    assert report.document.document_id == context.record.id
    assert report.document.metadata == context.record.metadata
    assert report.document.metadata.number == "SOP-00123"
    assert report.document.content == context.record.content
    assert report.document.source_provider == "mock-windchill"
    assert report.document.development_only is True
    assert report.document.page_count == 3


@pytest.mark.parametrize("state", ["In Work", "UNDERREVIEW", "Obsolete"])
def test_non_released_state_warning(state: str) -> None:
    report = assemble_summarize(_summarize_output(), _context(state=state))

    assert report.warnings[0] == (
        f"This document is in state '{state}', not Released. The analysis may not reflect "
        "the approved version."
    )


@pytest.mark.parametrize("state", ["Released", "released", " RELEASED ", None, ""])
def test_released_or_unknown_state_has_no_warning(state: str | None) -> None:
    assert record_warnings(make_record(make_extracted(PAGES), state=state).metadata) == []


def test_extraction_warnings_are_propagated_once() -> None:
    ocr_warning = (
        "Page 2 has no usable text layer and appears to be a scanned image; OCR is not "
        "available in this version."
    )
    extracted = ExtractedDocument(
        page_count=3,
        pages=[
            ExtractedPage(
                number=1, text=PAGES[0], char_count=80, has_text_layer=True, needs_ocr=False
            ),
            ExtractedPage(number=2, text="", char_count=0, has_text_layer=False, needs_ocr=True),
            ExtractedPage(
                number=3, text=PAGES[2], char_count=90, has_text_layer=True, needs_ocr=False
            ),
        ],
        extractor="test-extractor 1.0",
        warnings=[ocr_warning],
    )
    context = _context(extracted, state="In Work")
    record = context.record.model_copy(
        update={"extraction": ExtractionSummary.from_extracted(extracted)}
    )
    context = AssemblyContext(
        record=record,
        extracted=extracted,
        result_id=context.result_id,
        provenance=context.provenance,
    )

    report = assemble_summarize(_summarize_output(), context)

    assert report.warnings.count(ocr_warning) == 1
    assert report.warnings.index(ocr_warning) == 1  # after the state warning
    assert report.document.page_count == 3


# --- requirements / risks ----------------------------------------------------------------------


def test_requirements_report() -> None:
    output = LLMRequirementsOutput.model_validate(
        {
            "requirements": [_requirement(), _requirement("Wear glasses.", sources=[Q_GLASSES])],
            "limitations": [" Annex A not provided. "],
        }
    )

    report = assemble_requirements(output, _context(task="requirements"))

    assert report.task == "requirements"
    assert [r.id for r in report.requirements] == ["REQ-001", "REQ-002"]
    assert [c.id for c in report.citations] == ["C1", "C2"]
    assert report.verification.items_total == 2
    assert report.verification.items_without_verified_source == 0
    assert report.limitations == ["Annex A not provided."]


def test_risks_report() -> None:
    output = LLMRisksOutput.model_validate(
        {
            "risks": [_risk(sources=[Q_INVENTED]), _risk("Burns", severity="medium")],
            "limitations": [],
        }
    )

    report = assemble_risks(output, _context(task="risks"))

    assert report.task == "risks"
    assert [(r.id, r.severity) for r in report.risks] == [
        ("RISK-001", "high"),
        ("RISK-002", "medium"),
    ]
    assert report.verification.items_without_verified_source == 1
    assert "1 of 2 citations could not be verified against the document text." in report.warnings


# --- answers -----------------------------------------------------------------------------------


def test_answerable_answer() -> None:
    output = LLMAnswerOutput(
        answerable=True,
        answer="  Lock out and tag out the main power supply first. ",
        sources=[Q_LOTO, Q_LOTO],  # type: ignore[list-item]
    )

    response = assemble_answer(output, _context(task="ask", question="What first?"))

    assert response.answer_id == "r" * 32
    assert response.document_id == "0" * 31 + "1"
    assert response.question == "What first?"
    assert response.answer == "Lock out and tag out the main power supply first."
    assert [c.id for c in response.citations] == ["C1"]
    assert response.verification.items_total == 1
    assert response.verification.items_without_verified_source == 0
    assert response.warnings == []


def test_unanswerable_answer_without_sources() -> None:
    output = LLMAnswerOutput(answerable=False, answer="The document does not cover it.", sources=[])

    response = assemble_answer(output, _context(task="ask", question="Who approved it?"))

    assert response.answerable is False
    assert response.citations == []
    assert response.verification.items_total == 0
    assert response.verification.items_without_verified_source == 0


def test_answer_warnings_include_state_and_unverified_citations() -> None:
    output = LLMAnswerOutput.model_validate(
        {"answerable": True, "answer": "Yes.", "sources": [Q_INVENTED]}
    )

    response = assemble_answer(output, _context(state="In Work", task="ask", question="Q?"))

    assert response.warnings[0].startswith("This document is in state 'In Work'")
    assert "1 of 1 citation could not be verified against the document text." in response.warnings
    assert response.verification.items_without_verified_source == 1


def test_answer_requires_question() -> None:
    output = LLMAnswerOutput(answerable=False, answer="n/a", sources=[])

    with pytest.raises(ValueError, match="question"):
        assemble_answer(output, _context(task="ask"))


# --- cache rebinding ---------------------------------------------------------------------------


def test_rebind_to_record_replaces_document_and_state_warning() -> None:
    context = _context(state="In Work")
    output = _summarize_output(requirements=[_requirement(sources=[Q_INVENTED])])
    report = assemble_summarize(output, context)
    other = make_record(context.extracted, document_id="f" * 32, state="Released")

    rebound = rebind_to_record(report, other)

    assert rebound.document.document_id == "f" * 32
    assert not any(w.startswith("This document is in state") for w in rebound.warnings)
    assert any("could not be verified" in w for w in rebound.warnings)
    assert rebound.citations == report.citations
    assert rebound.report_id == report.report_id


def test_rebind_to_record_adds_state_warning_for_new_record() -> None:
    context = _context(state="Released")
    report = assemble_summarize(_summarize_output(), context)
    other = make_record(context.extracted, document_id="e" * 32, state="In Work")

    rebound = rebind_to_record(report, other)

    assert rebound.warnings == record_warnings(other.metadata)
