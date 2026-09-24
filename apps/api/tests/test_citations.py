"""Citation verification: normalization, exact/relocated/approximate matching and registry."""

from __future__ import annotations

import random
import time

import pytest

from conftest import make_extracted
from docintel.intelligence.citations import (
    APPROXIMATE_THRESHOLD,
    CitationMatch,
    CitationRegistry,
    CitationVerifier,
    normalize,
    normalize_quote,
)
from docintel.schemas.report import SourceQuote

PAGE_1 = (
    "1. Purpose\n"
    "This procedure defines the preventive maintenance of the hydraulic press HP-200 "
    "operated in Hall 3."
)
PAGE_2 = (
    "2. Safety\n"
    "WARNING: Lock out and tag out the main power supply before opening the guard.\n"
    "Operators must wear safety glasses and gloves at all times during mainte-\n"
    "nance work. Complete the pre-\nstart checklist before each shift."
)
PAGE_3 = (
    "3. Procedure\n"
    "The operator shall inspect the hydraulic hoses for leaks and damage before starting "
    "the machine at the beginning of each shift.\n"
    "The \u201chydraulic oil\u201d temperature must stay between 40\u201360 \u00b0C. "
    "Record the \ufb01nal reading in the maintenance log."
)


@pytest.fixture
def verifier() -> CitationVerifier:
    return CitationVerifier(make_extracted([PAGE_1, PAGE_2, PAGE_3]))


# --- normalization -----------------------------------------------------------------------------


def test_normalize_whitespace_and_case() -> None:
    assert normalize("  The  Operator\n\tSHALL\u00a0check  ") == "the operator shall check"


def test_normalize_quotes_dashes_and_ligatures() -> None:
    text = "\u201cQuoted\u201d \u2018single\u2019 40\u201360 a\u2014b \u22125 \ufb01lter \u2033"

    assert normalize(text) == '"quoted" \'single\' 40-60 a-b -5 filter "'


def test_normalize_removes_invisible_characters() -> None:
    assert normalize("main\u00adte\u200bnance\ufeff") == "maintenance"


def test_normalize_joins_line_break_hyphenation() -> None:
    assert normalize("mainte-\n  nance and soft\u00ad\nhyphen") == "maintenance and softhyphen"
    assert normalize("pre-\nstart", join_hyphenation=False) == "pre-start"
    # A hyphen that is not at a line break is kept.
    assert normalize("pre-start 40-60") == "pre-start 40-60"


def test_normalize_quote_strips_surrounding_punctuation() -> None:
    assert normalize_quote('  "\u2026the guard." ') == "the guard"
    assert normalize_quote("(see Section 4)") == "see section 4"


# --- exact matching ----------------------------------------------------------------------------


def test_exact_quote_on_cited_page_is_verified(verifier: CitationVerifier) -> None:
    result = verifier.verify(2, "Lock out and tag out the main power supply before opening")

    assert result == CitationMatch("verified", 2, 1.0)


@pytest.mark.parametrize(
    "quote",
    [
        "lock OUT and tag out   the main\npower supply",  # case and whitespace
        "\u201cLock out and tag out the main power supply.\u201d",  # surrounding quotes
        "WARNING:  Lock out and tag out",  # extra whitespace
    ],
)
def test_normalization_differences_still_verify(verifier: CitationVerifier, quote: str) -> None:
    assert verifier.verify(2, quote).status == "verified"


def test_typographic_differences_verify(verifier: CitationVerifier) -> None:
    # Straight quotes and hyphen-minus in the quote; curly quotes, en dash and "fi" ligature
    # in the document.
    quote = 'The "hydraulic oil" temperature must stay between 40-60 \u00b0C. Record the final'

    assert verifier.verify(3, quote).status == "verified"


def test_hyphenated_line_break_verifies(verifier: CitationVerifier) -> None:
    assert verifier.verify(2, "gloves at all times during maintenance work").status == "verified"


def test_real_hyphen_at_line_break_verifies(verifier: CitationVerifier) -> None:
    assert verifier.verify(2, "Complete the pre-start checklist before each shift").status == (
        "verified"
    )


def test_quote_on_another_page_is_relocated(verifier: CitationVerifier) -> None:
    result = verifier.verify(1, "inspect the hydraulic hoses for leaks and damage")

    assert result == CitationMatch("relocated", 3, 1.0)


def test_short_quote_exact_match(verifier: CitationVerifier) -> None:
    assert verifier.verify(2, "gloves").status == "verified"
    assert verifier.verify(1, "gloves") == CitationMatch("relocated", 2, 1.0)


def test_short_quote_without_exact_match_is_unverified(verifier: CitationVerifier) -> None:
    # Fewer than three words: no fuzzy matching, even though "glove" is close to "gloves".
    assert verifier.verify(2, "safety glovez") == CitationMatch("unverified", None, 0.0)


# --- approximate matching ----------------------------------------------------------------------


def test_few_changed_words_are_approximate(verifier: CitationVerifier) -> None:
    quote = (
        "The operator shall check the hydraulic hoses for leaks and wear before starting the "
        "machine at the beginning of each shift"
    )

    result = verifier.verify(3, quote)

    assert result.status == "approximate"
    assert result.matched_page == 3
    assert APPROXIMATE_THRESHOLD <= result.score < 1.0


def test_approximate_match_on_another_page(verifier: CitationVerifier) -> None:
    quote = "This procedure describes the preventive maintenance of the hydraulic press HP-200"

    result = verifier.verify(3, quote)

    assert result.status == "approximate"
    assert result.matched_page == 1


def test_paraphrase_is_unverified_with_best_score(verifier: CitationVerifier) -> None:
    quote = "Workers need to disconnect electricity prior to removing the protective cover"

    result = verifier.verify(2, quote)

    assert result.status == "unverified"
    assert result.matched_page is None
    assert 0.0 <= result.score < APPROXIMATE_THRESHOLD
    assert result.score == round(result.score, 3)


def test_invented_quote_is_unverified(verifier: CitationVerifier) -> None:
    result = verifier.verify(1, "Replace the conveyor belt every twelve months using kit 55")

    assert result.status == "unverified"
    assert result.matched_page is None


def test_very_long_quotes_are_not_fuzzy_matched(verifier: CitationVerifier) -> None:
    quote = " ".join(["maintenance"] * 61)

    assert verifier.verify(1, quote) == CitationMatch("unverified", None, 0.0)


def test_long_exact_quote_still_verifies() -> None:
    text = " ".join(f"word{i}" for i in range(100))
    verifier = CitationVerifier(make_extracted([text]))

    assert verifier.verify(1, text).status == "verified"


# --- invalid pages -----------------------------------------------------------------------------


@pytest.mark.parametrize("page", [0, -1, 4, 999])
def test_invalid_page(verifier: CitationVerifier, page: int) -> None:
    result = verifier.verify(page, "Replace the conveyor belt every twelve months using kit 55")

    assert result.status == "invalid_page"
    assert result.matched_page is None


def test_invalid_page_but_quote_found_elsewhere_is_relocated(verifier: CitationVerifier) -> None:
    assert verifier.verify(7, "wear safety glasses and gloves") == CitationMatch(
        "relocated", 2, 1.0
    )


def test_invalid_page_but_close_match_elsewhere_is_approximate(
    verifier: CitationVerifier,
) -> None:
    quote = "This procedure describes the preventive maintenance of the hydraulic press HP-200"

    result = verifier.verify(12, quote)

    assert result.status == "approximate"
    assert result.matched_page == 1


@pytest.mark.parametrize(("page", "status"), [(1, "unverified"), (9, "invalid_page")])
def test_empty_quote(verifier: CitationVerifier, page: int, status: str) -> None:
    assert verifier.verify(page, "  ...  ") == CitationMatch(status, None, 0.0)  # type: ignore[arg-type]


# --- ellipses ----------------------------------------------------------------------------------


@pytest.mark.parametrize("ellipsis", ["...", "\u2026", " . . . ", "[...]"])
def test_ellipsis_fragments_in_order_verify(verifier: CitationVerifier, ellipsis: str) -> None:
    quote = f"The operator shall inspect the hydraulic hoses{ellipsis}before starting the machine"

    assert verifier.verify(3, quote) == CitationMatch("verified", 3, 1.0)


def test_ellipsis_fragments_on_another_page_are_relocated(verifier: CitationVerifier) -> None:
    quote = "Lock out and tag out \u2026 before opening the guard"

    assert verifier.verify(3, quote) == CitationMatch("relocated", 2, 1.0)


def test_ellipsis_fragments_out_of_order_do_not_verify(verifier: CitationVerifier) -> None:
    quote = "before starting the machine ... The operator shall inspect the hydraulic hoses"

    assert verifier.verify(3, quote).status not in {"verified", "relocated"}


def test_ellipsis_fragments_across_pages_do_not_verify(verifier: CitationVerifier) -> None:
    quote = "Lock out and tag out the main power supply ... inspect the hydraulic hoses for leaks"

    assert verifier.verify(2, quote).status not in {"verified", "relocated"}


def test_ellipsis_in_document_text_matches_exactly() -> None:
    verifier = CitationVerifier(make_extracted(["Scope ....... 3 and more text here"]))

    assert verifier.verify(1, "Scope ....... 3 and more").status == "verified"


# --- document context escape -------------------------------------------------------------------


def test_quote_copied_from_escaped_context_verifies() -> None:
    verifier = CitationVerifier(make_extracted(["Do not type </page> into the form field."]))

    assert verifier.verify(1, "Do not type \u2039/page> into the form").status == "verified"


# --- performance -------------------------------------------------------------------------------


def test_fuzzy_search_effort_is_bounded() -> None:
    rng = random.Random(7)
    vocabulary = [
        *("the", "operator", "shall", "ensure", "that", "machine", "is", "valve", "pump"),
        *("oil", "pressure", "check", "inspect", "before", "after", "each", "shift", "hose"),
        *("leak", "temperature", "record", "log", "clean", "safety", "guard"),
    ]
    pages = [" ".join(rng.choice(vocabulary) for _ in range(400)) for _ in range(150)]
    verifier = CitationVerifier(make_extracted(pages))
    quotes = [" ".join(rng.choice(vocabulary) for _ in range(20)) for _ in range(10)]

    started = time.perf_counter()
    for quote in quotes:
        verifier.verify(5, quote)
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0  # typically well under a second


def test_fuzzy_match_is_found_deep_in_a_long_document() -> None:
    rng = random.Random(3)
    filler = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota"]
    pages = [" ".join(rng.choice(filler) for _ in range(300)) for _ in range(120)]
    pages[99] += " Torque the pump flange bolts to 45 Nm in a cross pattern and log the value."
    verifier = CitationVerifier(make_extracted(pages))

    result = verifier.verify(4, "Torque the pump flange bolts to 40 Nm in a star pattern and log")

    assert result.status == "approximate"
    assert result.matched_page == 100


# --- registry ----------------------------------------------------------------------------------


def test_registry_assigns_ids_in_first_seen_order(verifier: CitationVerifier) -> None:
    registry = CitationRegistry(verifier)

    first = registry.register(
        [
            SourceQuote(page=2, quote="Lock out and tag out the main power supply"),
            SourceQuote(page=3, quote="inspect the hydraulic hoses"),
        ]
    )
    second = registry.register([SourceQuote(page=1, quote="preventive maintenance")])

    assert first == ["C1", "C2"]
    assert second == ["C3"]
    assert [c.id for c in registry.citations] == ["C1", "C2", "C3"]


def test_registry_deduplicates_by_page_and_normalized_quote(verifier: CitationVerifier) -> None:
    registry = CitationRegistry(verifier)

    a = registry.register([SourceQuote(page=2, quote="Lock out and tag out")])
    b = registry.register([SourceQuote(page=2, quote="  lock OUT and   tag out. ")])
    c = registry.register([SourceQuote(page=3, quote="Lock out and tag out")])

    assert a == b == ["C1"]
    assert c == ["C2"]  # same quote, different cited page -> separate citation
    assert registry.citations[0].quote == "Lock out and tag out"  # first-seen text is kept
    assert registry.citations[1].status == "relocated"
    assert registry.citations[1].matched_page == 2


def test_registry_dedupes_within_one_item_and_skips_empty_quotes(
    verifier: CitationVerifier,
) -> None:
    registry = CitationRegistry(verifier)

    ids = registry.register(
        [
            SourceQuote(page=2, quote="tag out the main power"),
            SourceQuote(page=1, quote="   "),
            SourceQuote(page=2, quote="Tag out the main power"),
        ]
    )

    assert ids == ["C1"]
    assert len(registry.citations) == 1


def test_registry_citation_fields(verifier: CitationVerifier) -> None:
    registry = CitationRegistry(verifier)

    registry.register([SourceQuote(page=5, quote=" A quote that is not in the document at all ")])
    citation = registry.citations[0]

    assert citation.page == 5
    assert citation.quote == "A quote that is not in the document at all"
    assert citation.status == "invalid_page"
    assert citation.matched_page is None
    assert 0.0 <= citation.match_score <= 1.0
    assert registry.status("C1") == "invalid_page"
