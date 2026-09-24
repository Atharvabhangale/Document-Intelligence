"""DevFakeLLMProvider: schema-valid, citation-verifiable, deterministic output."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from docintel.core.errors import AIProviderError
from docintel.providers.llm import dev_fake
from docintel.providers.llm.base import LLMRequest
from docintel.providers.llm.dev_fake import DevFakeLLMProvider
from docintel.schemas.report import (
    LLMAnswerOutput,
    LLMModel,
    LLMRequirementsOutput,
    LLMRisksOutput,
    LLMSummarizeOutput,
    SourceQuote,
    llm_json_schema,
)

OUTPUT_MODELS: dict[str, type[LLMModel]] = {
    "summarize": LLMSummarizeOutput,
    "requirements": LLMRequirementsOutput,
    "risks": LLMRisksOutput,
    "ask": LLMAnswerOutput,
}

PAGES = [
    "SOP-00123 Machine Maintenance SOP Rev A.3\n"
    "1. PURPOSE\n"
    "This procedure defines the preventive maintenance of the hydraulic press line HP-200.\n"
    "It applies to all maintenance technicians at Plant 2.\n"
    "2. SAFETY\n"
    "WARNING: The hydraulic system remains pressurized after shutdown and can cause\n"
    "serious injury. Operators shall wear safety glasses and gloves at all times. Do not bypass\n"
    "the light curtain.",
    "3. PROCEDURE\n"
    "3.1 Verify that the hydraulic oil temperature is between 40-60 °C before starting.\n"
    "3.2 Tighten the clamp bolts to 45 N·m in a cross pattern.\n"
    "3.3 The filter should be replaced every 500 h or 6 months, whichever comes first.\n"
    "CAUTION\n"
    "Failure to purge air from the lines may damage the pump.\n"
    "Record all measurements in the maintenance log (form QF-17) & sign the checklist.",
    "",
]


def render(pages: list[str]) -> str:
    """Render pages the way the pipeline does: ``<page number="N">text</page>`` elements."""
    parts = []
    for number, text in enumerate(pages, start=1):
        if text:
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f'<page number="{number}">{escaped}</page>')
        else:
            parts.append(f'<page number="{number}" status="no-text"></page>')
    return "<document>\n" + "\n".join(parts) + "\n</document>"


def make_request(
    schema_name: str,
    *,
    pages: list[str] = PAGES,
    instruction: str = "Return JSON that matches the required schema exactly.",
    context: str | None = None,
) -> LLMRequest:
    return LLMRequest(
        system="You are a document analyst.",
        document_context=context if context is not None else render(pages),
        instruction=instruction,
        json_schema=llm_json_schema(OUTPUT_MODELS.get(schema_name, LLMAnswerOutput)),
        schema_name=schema_name,
        max_output_tokens=16000,
        temperature=0.0,
    )


def ask(question: str, pages: list[str] = PAGES) -> LLMAnswerOutput:
    instruction = f"Answer the question.\n<question>{question}</question>"
    response = DevFakeLLMProvider().generate_json(
        make_request("ask", pages=pages, instruction=instruction)
    )
    return LLMAnswerOutput.model_validate_json(response.text)


def generate(schema_name: str, pages: list[str] = PAGES) -> Any:
    response = DevFakeLLMProvider().generate_json(make_request(schema_name, pages=pages))
    return OUTPUT_MODELS[schema_name].model_validate_json(response.text)


def iter_sources(node: Any) -> Iterator[SourceQuote]:
    """Every SourceQuote anywhere in an output model."""
    if isinstance(node, SourceQuote):
        yield node
    elif isinstance(node, LLMModel):
        for name in type(node).model_fields:
            yield from iter_sources(getattr(node, name))
    elif isinstance(node, list):
        for item in node:
            yield from iter_sources(item)


# --- Contract ---------------------------------------------------------------------------------


def test_identity() -> None:
    provider = DevFakeLLMProvider()

    assert provider.name == "fake"
    assert provider.model == "dev-fake-1"
    assert provider.development_only is True
    assert provider.configured is True


@pytest.mark.parametrize("schema_name", sorted(OUTPUT_MODELS))
def test_output_validates_against_llm_model(schema_name: str) -> None:
    request = make_request(schema_name)
    if schema_name == "ask":
        request = make_request(
            "ask", instruction="<question>What oil temperature is required?</question>"
        )

    response = DevFakeLLMProvider().generate_json(request)

    OUTPUT_MODELS[schema_name].model_validate_json(response.text)  # strict: no extra fields
    assert response.provider == "fake"
    assert response.model == "dev-fake-1"
    assert response.finish_reason == "end"
    assert response.usage.input_tokens and response.usage.output_tokens


@pytest.mark.parametrize("schema_name", sorted(OUTPUT_MODELS))
def test_output_uses_camel_case_aliases(schema_name: str) -> None:
    text = DevFakeLLMProvider().generate_json(make_request(schema_name)).text

    assert "key_points" not in text
    if schema_name == "summarize":
        assert '"keyPoints"' in text


@pytest.mark.parametrize("schema_name", ["summarize", "requirements", "risks"])
def test_quotes_are_exact_substrings_of_cited_pages(schema_name: str) -> None:
    output = generate(schema_name)

    sources = list(iter_sources(output))
    assert sources
    for source in sources:
        assert 1 <= source.page <= len(PAGES)
        assert source.quote in PAGES[source.page - 1], source
        assert 5 <= len(source.quote.split()) <= 25, source


@pytest.mark.parametrize("schema_name", sorted(OUTPUT_MODELS))
def test_deterministic(schema_name: str) -> None:
    request = make_request(schema_name, instruction="<question>How often is the filter?</question>")
    provider = DevFakeLLMProvider()

    assert provider.generate_json(request).text == provider.generate_json(request).text
    assert DevFakeLLMProvider().generate_json(request).text == provider.generate_json(request).text


def test_unsupported_task_is_rejected() -> None:
    with pytest.raises(AIProviderError) as info:
        DevFakeLLMProvider().generate_json(make_request("translate"))

    assert info.value.retryable is False


def test_delay_is_simulated_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(dev_fake.time, "sleep", sleeps.append)

    DevFakeLLMProvider().generate_json(make_request("risks"))
    DevFakeLLMProvider(delay_seconds=0.25).generate_json(make_request("risks"))

    assert sleeps == [0.25]


# --- Heuristics -------------------------------------------------------------------------------


def test_requirements_by_keyword() -> None:
    output = generate("requirements")

    by_statement = {r.statement: r for r in output.requirements}
    glasses = by_statement["Operators shall wear safety glasses and gloves at all times."]
    assert glasses.obligation == "mandatory"
    assert glasses.basis == "explicit"
    assert glasses.category == "Safety"
    assert glasses.sources[0].page == 1
    assert by_statement["Do not bypass the light curtain."].obligation == "mandatory"
    filter_statement = next(r for r in output.requirements if "filter" in r.statement)
    assert filter_statement.obligation == "recommended"
    # "... may damage the pump" is a risk statement, not a permission.
    assert not any("purge" in r.statement for r in output.requirements)
    assert output.limitations[0].startswith("Generated by the development-only fake AI provider")
    assert any("Page(s) 3" in note for note in output.limitations)


def test_specifications_value_and_unit() -> None:
    output = generate("summarize")

    specs = {(s.parameter, s.value, s.unit) for s in output.specifications}
    assert ("Hydraulic oil temperature", "40-60", "°C") in specs
    assert any(value == "45" and unit == "N·m" for _, value, unit in specs)
    assert any(value == "500" and unit == "h" for _, value, unit in specs)
    assert any(value == "6" and unit == "months" for _, value, unit in specs)
    oil = next(s for s in output.specifications if s.value == "40-60")
    assert oil.context == "3. PROCEDURE"
    assert oil.sources[0].page == 2


def test_risks_and_derived_actions() -> None:
    output = generate("summarize")

    warning = next(r for r in output.risks if "pressurized" in r.description)
    assert warning.severity == "high"
    assert warning.basis == "explicit"
    assert warning.title.startswith("Warning:")
    caution = next(r for r in output.risks if "purge" in r.description)
    assert caution.severity == "medium"
    assert 2 <= len(output.actions) <= 3
    assert all(action.basis == "inferred" for action in output.actions)
    assert output.actions[0].priority == "high"


def test_summary_purpose_and_key_points() -> None:
    output = generate("summarize")

    assert output.summary.purpose == (
        "This procedure defines the preventive maintenance of the hydraulic press line HP-200."
    )
    assert "It applies to all maintenance technicians at Plant 2." in output.summary.executive.text
    assert output.summary.executive.sources
    assert 3 <= len(output.summary.key_points) <= 5
    assert all(point.sources for point in output.summary.key_points)


def test_list_sizes_are_capped() -> None:
    pages = [" ".join(f"Step {i} shall be completed by the operator." for i in range(30))]

    output = generate("requirements", pages=pages)

    assert len(output.requirements) == dev_fake.MAX_ITEMS
    assert any("Only the first 10 of 30" in note for note in output.limitations)


def test_long_sentence_quote_is_windowed_around_keyword() -> None:
    filler = " ".join(f"word{i}" for i in range(40))
    sentence = f"Before the shift {filler} the operator must lock the main isolator {filler}."

    output = generate("requirements", pages=[sentence])

    quote = output.requirements[0].sources[0].quote
    assert quote in sentence
    assert "must" in quote
    assert len(quote.split()) == 25


def test_short_sentence_quote_is_extended_to_five_words() -> None:
    page = "You must wear gloves.\nThen continue with the next step of the procedure."

    output = generate("requirements", pages=[page])

    assert output.requirements[0].statement == "You must wear gloves."
    quote = output.requirements[0].sources[0].quote
    assert quote in page
    assert quote.startswith("You must wear gloves.")
    assert len(quote.split()) == 5


def test_empty_document_produces_valid_empty_report() -> None:
    output = generate("summarize", pages=["", ""])

    assert output.requirements == output.risks == output.specifications == output.actions == []
    assert output.summary.key_points == []
    assert any("Page(s) 1, 2" in note for note in output.limitations)


def test_tolerant_page_parsing() -> None:
    context = (
        "<document number='SOP-1'>"
        "<page number='1' label=\"i\">Operators must wear gloves during every cleaning task.</page>"
        '<page number="2" status="no-text"/>'
        '<page status="ok" number="3">Operators should inspect the guard before each shift.</page>'
        "</document>"
    )

    response = DevFakeLLMProvider().generate_json(make_request("requirements", context=context))

    output = LLMRequirementsOutput.model_validate_json(response.text)
    assert [r.sources[0].page for r in output.requirements] == [1, 3]
    assert any("Page(s) 2" in note for note in output.limitations)


def test_escaped_text_is_decoded_so_quotes_match_raw_page_text() -> None:
    page = "Operators must record the torque value & sign the form <QF-17> before release."

    output = generate("requirements", pages=[page])

    assert output.requirements[0].sources[0].quote in page


# --- Ask --------------------------------------------------------------------------------------


def test_ask_answerable_cites_best_matching_sentence() -> None:
    answer = ask("What hydraulic oil temperature is required before starting?")

    assert answer.answerable is True
    assert "40-60 °C" in answer.answer
    assert answer.sources
    assert answer.sources[0].page == 2
    assert all(s.quote in PAGES[s.page - 1] for s in answer.sources)


def test_ask_unanswerable_when_no_keyword_overlap() -> None:
    answer = ask("What is the capital of France?")

    assert answer.answerable is False
    assert answer.sources == []
    assert "does not appear to contain" in answer.answer


def test_ask_without_question_tag_uses_instruction() -> None:
    response = DevFakeLLMProvider().generate_json(
        make_request("ask", instruction="How often should the filter be replaced?")
    )

    answer = LLMAnswerOutput.model_validate_json(response.text)
    assert answer.answerable is True
    assert "500 h" in answer.answer
