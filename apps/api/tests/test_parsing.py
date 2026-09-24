"""Parsing and validation of raw LLM output, including malformed output."""

from __future__ import annotations

import json
from typing import Any

import pytest

from docintel.intelligence.parsing import (
    MAX_PROBLEMS,
    OutputValidationFailure,
    parse_llm_output,
)
from docintel.schemas.report import (
    LLMAnswerOutput,
    LLMRequirementsOutput,
    LLMRisksOutput,
    LLMSummarizeOutput,
)

ANSWER: dict[str, Any] = {
    "answerable": True,
    "answer": "Lock out the main power supply.",
    "sources": [{"page": 2, "quote": "Lock out and tag out the main power supply"}],
}


def _requirement(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "statement": "Wear safety glasses.",
        "basis": "explicit",
        "obligation": "mandatory",
        "category": "Safety",
        "sources": [{"page": 1, "quote": "Operators must wear safety glasses"}],
    }
    item.update(overrides)
    return item


def _summarize() -> dict[str, Any]:
    return {
        "summary": {
            "purpose": "Defines maintenance.",
            "executive": {"text": "Summary.", "sources": [{"page": 1, "quote": "a b c"}]},
            "keyPoints": [{"text": "Point.", "sources": []}],
        },
        "requirements": [_requirement()],
        "specifications": [
            {
                "parameter": "Oil temperature",
                "value": "40-60",
                "unit": "\u00b0C",
                "context": None,
                "sources": [],
            }
        ],
        "risks": [
            {
                "title": "Crush hazard",
                "description": "Moving parts.",
                "severity": "high",
                "basis": "explicit",
                "sources": [],
            }
        ],
        "actions": [],
        "limitations": [],
    }


def _failure(text: str, model: type = LLMAnswerOutput) -> OutputValidationFailure:
    with pytest.raises(OutputValidationFailure) as info:
        parse_llm_output(text, model)
    return info.value


# --- accepted output ---------------------------------------------------------------------------


def test_valid_json() -> None:
    result = parse_llm_output(json.dumps(ANSWER), LLMAnswerOutput)

    assert isinstance(result, LLMAnswerOutput)
    assert result.answerable is True
    assert result.sources[0].page == 2


def test_valid_summarize_output_with_camel_case_keys() -> None:
    result = parse_llm_output(json.dumps(_summarize()), LLMSummarizeOutput)

    assert result.summary.key_points[0].text == "Point."
    assert result.specifications[0].unit == "\u00b0C"


def test_surrounding_whitespace() -> None:
    assert parse_llm_output("\n\n  " + json.dumps(ANSWER) + "  \n", LLMAnswerOutput).answerable


@pytest.mark.parametrize("fence", ["```json", "```JSON", "```", "``` json"])
def test_fenced_json(fence: str) -> None:
    text = f"{fence}\n{json.dumps(ANSWER, indent=2)}\n```"

    assert parse_llm_output(text, LLMAnswerOutput).answer == ANSWER["answer"]


def test_fenced_json_on_one_line() -> None:
    assert parse_llm_output(f"```json {json.dumps(ANSWER)}```", LLMAnswerOutput).answerable


def test_leading_and_trailing_prose_around_object() -> None:
    text = f"Here is the analysis you asked for:\n{json.dumps(ANSWER)}\nLet me know if..."

    assert parse_llm_output(text, LLMAnswerOutput).answer == ANSWER["answer"]


def test_prose_around_fenced_object() -> None:
    text = f"Sure!\n```json\n{json.dumps(ANSWER)}\n```\nDone."

    assert parse_llm_output(text, LLMAnswerOutput).answerable


def test_numeric_string_page_is_coerced() -> None:
    data = {**ANSWER, "sources": [{"page": "3", "quote": "x y z"}]}

    assert parse_llm_output(json.dumps(data), LLMAnswerOutput).sources[0].page == 3


# --- malformed output --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   \n\t"])
def test_empty_output(text: str) -> None:
    failure = _failure(text)

    assert failure.kind == "empty"
    assert failure.problems == ["(root): the response was empty"]


def test_truncated_json() -> None:
    text = json.dumps(_summarize())[:-40]

    failure = _failure(text, LLMSummarizeOutput)

    assert failure.kind == "invalid_json"
    assert len(failure.problems) == 1
    assert failure.problems[0].startswith("(root): the response is not valid JSON (")
    assert "line 1 column" in failure.problems[0]
    assert "Oil temperature" not in failure.problems[0]  # content is never echoed


def test_not_json_at_all() -> None:
    failure = _failure("I'm sorry, I cannot produce JSON for this document.")

    assert failure.kind == "invalid_json"
    assert "cannot produce" not in failure.feedback()


def test_prose_with_broken_object() -> None:
    failure = _failure('Result: {"answerable": true, "answer": "x", "sources": [}')

    assert failure.kind == "invalid_json"


@pytest.mark.parametrize(
    ("text", "type_name"),
    [("[1, 2]", "an array"), ('"just a string"', "a string"), ("42", "a number"), ("null", "null")],
)
def test_top_level_value_must_be_an_object(text: str, type_name: str) -> None:
    failure = _failure(text)

    assert failure.kind == "not_object"
    assert failure.problems == [f"(root): expected a JSON object, got {type_name}"]


def test_wrong_types() -> None:
    data = {"answerable": "perhaps", "answer": 12, "sources": {"page": 1}}

    failure = _failure(json.dumps(data))

    assert failure.kind == "schema"
    assert set(failure.paths) == {"answerable", "answer", "sources"}
    assert any(
        p.startswith("answerable: Input should be a valid boolean") for p in failure.problems
    )
    assert any(p.startswith("answer: Input should be a valid string") for p in failure.problems)
    assert any(p.startswith("sources: Input should be a valid list") for p in failure.problems)


def test_missing_required_fields() -> None:
    data = _summarize()
    del data["summary"]["keyPoints"]
    del data["limitations"]

    failure = _failure(json.dumps(data), LLMSummarizeOutput)

    assert "summary.keyPoints: Field required" in failure.problems
    assert "limitations: Field required" in failure.problems
    assert failure.total == 2


def test_nullable_fields_are_still_required() -> None:
    item = _requirement()
    del item["category"]

    failure = _failure(
        json.dumps({"requirements": [item], "limitations": []}), LLMRequirementsOutput
    )

    assert failure.problems == ["requirements[0].category: Field required"]


def test_extra_fields_are_forbidden() -> None:
    data = {**ANSWER, "confidence": 0.9, "sources": [{"page": 1, "quote": "q", "line": 4}]}

    failure = _failure(json.dumps(data))

    assert "confidence: Extra inputs are not permitted" in failure.problems
    assert "sources[0].line: Extra inputs are not permitted" in failure.problems


def test_wrong_enum_values() -> None:
    risk = {
        "title": "Burn",
        "description": "Hot oil.",
        "severity": "critical",
        "basis": "guessed",
        "sources": [],
    }

    failure = _failure(json.dumps({"risks": [risk], "limitations": []}), LLMRisksOutput)

    assert "risks[0].severity: Input should be 'high', 'medium' or 'low'" in failure.problems
    assert "risks[0].basis: Input should be 'explicit' or 'inferred'" in failure.problems


def test_nested_errors_have_readable_paths() -> None:
    data = {
        "requirements": [
            _requirement(),
            _requirement(sources=[{"page": "three", "quote": "x"}, {"page": 2}]),
        ],
        "limitations": [None],
    }

    failure = _failure(json.dumps(data), LLMRequirementsOutput)

    assert failure.paths == [
        "requirements[1].sources[0].page",
        "requirements[1].sources[1].quote",
        "limitations[0]",
    ]
    assert failure.problems[0].startswith(
        "requirements[1].sources[0].page: Input should be a valid integer"
    )


def test_problem_list_is_capped() -> None:
    data = {"requirements": [{"statement": i} for i in range(10)], "limitations": []}

    failure = _failure(json.dumps(data), LLMRequirementsOutput)

    # Each item: wrong statement type + 4 missing fields = 5 problems -> 50 in total.
    assert failure.total == 50
    assert len(failure.problems) == MAX_PROBLEMS + 1
    assert failure.problems[-1] == f"... and {50 - MAX_PROBLEMS} more problem(s)"
    assert len(failure.paths) == MAX_PROBLEMS


def test_problems_never_include_input_values() -> None:
    secret_like = "DOCUMENT TEXT: confidential torque value 45 Nm"
    data = {"answerable": secret_like, "answer": ["x"], "sources": [{"page": secret_like}]}

    failure = _failure(json.dumps(data))

    assert secret_like not in failure.feedback()
    assert "45 Nm" not in str(failure)


def test_long_extra_key_names_are_truncated() -> None:
    data = {**ANSWER, "k" * 500: 1}

    failure = _failure(json.dumps(data))

    assert len(failure.problems[0]) < 120


def test_feedback_is_a_bullet_list() -> None:
    failure = _failure(json.dumps({"answerable": True}))

    assert failure.feedback() == "- answer: Field required\n- sources: Field required"


def test_failure_message_is_generic() -> None:
    failure = _failure("not json")

    assert str(failure) == "LLM output failed validation (invalid_json, 1 problem(s))"
