"""Tests for the synthetic sample SOP PDFs (samples/*.pdf) and their generator.

The samples back the DEVELOPMENT ONLY mock Windchill provider. They must exist for every
catalog entry, extract cleanly, print the catalog metadata and contain the facts (and the
deliberate gaps) that the rest of the system and its demos rely on.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from docintel.core.config import REPO_ROOT
from docintel.core.models import ExtractedDocument
from docintel.extraction import PdfPlumberExtractor

SAMPLES_DIR = REPO_ROOT / "samples"
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_samples.py"
CATALOG: dict[str, Any] = json.loads((SAMPLES_DIR / "catalog.json").read_text(encoding="utf-8"))
ENTRIES: list[dict[str, Any]] = CATALOG["documents"]
ENTRY_IDS = [entry["metadata"]["number"] for entry in ENTRIES]

# Inclusive page-count ranges per document.
EXPECTED_PAGES = {
    "SOP-00123": (5, 6),
    "SOP-00087": (3, 5),
    "SOP-00141": (2, 4),
    "SOP-00056": (4, 5),
}
SCANNED_PAGES = {"SOP-00056": [3]}


def version(entry: dict[str, Any]) -> str:
    meta = entry["metadata"]
    return f"{meta['revision']}.{meta['iteration']}"


@pytest.fixture(scope="module")
def extracted() -> dict[str, ExtractedDocument]:
    extractor = PdfPlumberExtractor()
    return {
        entry["metadata"]["number"]: extractor.extract(
            (SAMPLES_DIR / entry["file"]).read_bytes(), max_pages=300
        )
        for entry in ENTRIES
    }


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def pages_containing(doc: ExtractedDocument, phrase: str) -> list[int]:
    """Pages whose text contains ``phrase``; line breaks count as spaces."""
    wanted = _collapse(phrase)
    return [page.number for page in doc.pages if wanted in _collapse(page.text)]


def section_text(doc: ExtractedDocument, start: str, end: str) -> str:
    """Text between two headings (e.g. "3 References" and "4 Responsibilities")."""
    full = "\n".join(page.text for page in doc.pages)
    match = re.search(rf"^{re.escape(start)}$(.*?)^{re.escape(end)}$", full, re.M | re.S)
    assert match, f"section {start!r} not found"
    return match.group(1)


# --- Catalog and files ----------------------------------------------------------------------


def test_catalog_lists_the_expected_documents() -> None:
    assert CATALOG["developmentOnly"] is True
    assert sorted(ENTRY_IDS) == sorted(EXPECTED_PAGES)


@pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
def test_every_catalog_entry_has_its_pdf(entry: dict[str, Any]) -> None:
    path = SAMPLES_DIR / entry["file"]
    assert path.is_file(), f"missing {path}; run scripts/generate_samples.py"
    assert path.read_bytes().startswith(b"%PDF-")


# --- Extraction -----------------------------------------------------------------------------


@pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
def test_sample_extracts_with_expected_page_count(
    entry: dict[str, Any], extracted: dict[str, ExtractedDocument]
) -> None:
    number = entry["metadata"]["number"]
    doc = extracted[number]
    low, high = EXPECTED_PAGES[number]
    assert low <= doc.page_count <= high
    assert [page.number for page in doc.pages] == list(range(1, doc.page_count + 1))
    assert doc.total_chars > 5000
    assert doc.pages_needing_ocr == SCANNED_PAGES.get(number, [])


@pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
def test_footer_page_numbers_match_physical_pages(
    entry: dict[str, Any], extracted: dict[str, ExtractedDocument]
) -> None:
    doc = extracted[entry["metadata"]["number"]]
    for page in doc.pages:
        if page.needs_ocr:
            continue
        assert f"Page {page.number} of {doc.page_count}" in page.text
        assert "Synthetic sample \u2013 development only" in page.text


@pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
def test_first_page_shows_catalog_metadata(
    entry: dict[str, Any], extracted: dict[str, ExtractedDocument]
) -> None:
    meta = entry["metadata"]
    first = extracted[meta["number"]].pages[0].text
    assert f"Document number {meta['number']}" in first
    assert f"Title {meta['name']}" in first
    assert f"Revision {version(entry)} (revision {meta['revision']}" in first
    assert f"Lifecycle state {meta['state']}" in first


@pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
def test_header_on_every_text_page(
    entry: dict[str, Any], extracted: dict[str, ExtractedDocument]
) -> None:
    meta = entry["metadata"]
    header = f"{meta['number']} | Rev. {version(entry)} | {meta['state']}"
    for page in extracted[meta["number"]].pages:
        if not page.needs_ocr:
            assert page.text.startswith(f"NORTHWIND INDUSTRIAL {header}\n{meta['name']}")


@pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
def test_standard_sections_in_order(
    entry: dict[str, Any], extracted: dict[str, ExtractedDocument]
) -> None:
    doc = extracted[entry["metadata"]["number"]]
    full = "\n".join(page.text for page in doc.pages)
    headings = [
        "1 Purpose",
        "2 Scope",
        "3 References",
        "4 Responsibilities",
        "5 Safety / PPE",
        "6 Tools & Materials",
        "7 Procedure",
        "8 Inspection & Acceptance Criteria",
        "9 Records",
        "10 Revision History",
    ]
    positions = [re.search(rf"^{re.escape(h)}$", full, re.M) for h in headings]
    assert all(positions), [h for h, p in zip(headings, positions, strict=True) if not p]
    starts = [p.start() for p in positions if p]
    assert starts == sorted(starts)


# --- Document-specific content --------------------------------------------------------------


def test_sop_00056_page_3_is_a_scanned_image(extracted: dict[str, ExtractedDocument]) -> None:
    doc = extracted["SOP-00056"]
    page = doc.pages[2]
    assert page.number == 3
    assert page.needs_ocr
    assert not page.has_text_layer
    assert page.char_count == 0
    assert any("Page 3 has no usable text layer" in w for w in doc.warnings)
    # The acceptance criteria on page 4 still carry the key limits as text.
    assert pages_containing(doc, "8.5\u20139.2") == [4]
    assert "6\u20138 %" in doc.pages[1].text


def test_sop_00123_contains_checkable_specifications(
    extracted: dict[str, ExtractedDocument],
) -> None:
    doc = extracted["SOP-00123"]
    assert any("55" in p.text and "bar" in p.text for p in doc.pages)
    for phrase in (
        "55\u201365 bar",
        "ISO VG 46",
        "40\u201360 \u00b0C",
        "6\u20138 %",
        "45 N\u00b7m",
        "500 operating hours",
        "at least 12 kN",
        "88\u201396 Hz",
        "retained for 3 years",
        "SOP-00087",
    ):
        assert pages_containing(doc, phrase), phrase


def test_sop_00123_contains_the_deliberate_gaps(extracted: dict[str, ExtractedDocument]) -> None:
    doc = extracted["SOP-00123"]
    # Vague filter instruction that conflicts with the 500-hour replacement rule.
    assert pages_containing(doc, "Inspect filters regularly")
    # WI-2210 is used in the procedure but missing from the References section.
    assert pages_containing(doc, "WI-2210 Spindle")
    assert "WI-2210" not in section_text(doc, "3 References", "4 Responsibilities")
    # Spindle runout is checked without a stated tolerance.
    procedure = section_text(doc, "7 Procedure", "8 Inspection & Acceptance Criteria")
    runout = procedure[procedure.index("7.2.7 Spindle runout") : procedure.index("7.2.8")]
    assert "\u00b5m" not in runout
    assert "tolerance" not in runout
    criteria = section_text(doc, "8 Inspection & Acceptance Criteria", "9 Records")
    assert "runout" not in criteria.lower()


def test_sop_00087_covers_loto_essentials(extracted: dict[str, ExtractedDocument]) -> None:
    doc = extracted["SOP-00087"]
    for phrase in (
        "Authorized employee",
        "Affected employee",
        "Hydraulic accumulators shall be bled down",
        "zero energy",
        "group lock box",
        "at least annually",
        "refresher training every 3 years",
    ):
        assert pages_containing(doc, phrase), phrase


def test_sop_00141_is_marked_as_draft(extracted: dict[str, ExtractedDocument]) -> None:
    doc = extracted["SOP-00141"]
    assert pages_containing(doc, "DRAFT \u2013 IN WORK") == list(range(1, doc.page_count + 1))
    for phrase in ("250 t", "80 % of the rated press capacity", "light curtain", "TBD"):
        assert pages_containing(doc, phrase), phrase


# --- Generator ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def generator() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("generate_samples", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve annotations through sys.modules, so register before executing.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_generator_is_deterministic_and_matches_committed_samples(
    generator: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extracted: dict[str, ExtractedDocument],
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    assert generator.main(["--out", str(first)]) == 0
    assert generator.main(["--out", str(second)]) == 0

    output = capsys.readouterr().out
    extractor = PdfPlumberExtractor()
    for entry in ENTRIES:
        name = entry["file"]
        assert name in output
        data = (first / name).read_bytes()
        assert data == (second / name).read_bytes(), f"{name} is not deterministic"
        # Byte equality with the committed files can depend on the zlib build, so compare
        # the extracted text instead: the committed samples must be up to date.
        regenerated = extractor.extract(data, max_pages=300)
        committed = extracted[entry["metadata"]["number"]]
        assert [p.text for p in regenerated.pages] == [p.text for p in committed.pages], (
            f"{name} is out of date; run scripts/generate_samples.py"
        )
