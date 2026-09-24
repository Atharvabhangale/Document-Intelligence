"""Tests for the pdfplumber text extractor (docintel.extraction.pdf)."""

from __future__ import annotations

import io
import logging
import re

import pdfplumber
import pytest
from pdfplumber.page import Page
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from docintel.core.errors import (
    DocumentTooLargeError,
    EncryptedDocumentError,
    ExtractionError,
    NoExtractableTextError,
    UnsupportedMediaTypeError,
)
from docintel.extraction import (
    OcrEngine,
    PdfPlumberExtractor,
    TextExtractor,
    get_default_extractor,
    normalize_text,
)
from docintel.extraction.pdf import format_page_numbers, looks_like_pdf
from pdf_factory import make_pdf, make_pdf_with_image_page

MAX_PAGES = 50
SCANNED_WARNING = (
    "Page {n} has no usable text layer and appears to be a scanned image; "
    "OCR is not available in this version."
)


@pytest.fixture
def extractor() -> PdfPlumberExtractor:
    return PdfPlumberExtractor()


class FakeOcr(OcrEngine):
    """Records calls and returns canned text (or raises) per page."""

    name = "fake-ocr 1.0"

    def __init__(self, result: str | Exception = "") -> None:
        self.result = result
        self.calls: list[tuple[bytes, int]] = []

    def ocr_page(self, pdf_bytes: bytes, page_number: int) -> str:
        self.calls.append((pdf_bytes, page_number))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result.format(n=page_number)


# --- Identity -------------------------------------------------------------------------------


def test_name_reports_pdfplumber_version(extractor: PdfPlumberExtractor) -> None:
    assert extractor.name == f"pdfplumber {pdfplumber.__version__}"
    assert re.fullmatch(r"pdfplumber \d+\.\d+\.\d+\S*", extractor.name)


def test_default_extractor_is_pdfplumber() -> None:
    default = get_default_extractor()
    assert isinstance(default, TextExtractor)
    assert isinstance(default, PdfPlumberExtractor)


# --- Page separation ------------------------------------------------------------------------


def test_each_page_text_lands_on_its_physical_page(extractor: PdfPlumberExtractor) -> None:
    pages = [
        "Hydraulic pressure shall be 55-65 bar at gauge PG-1.",
        "Lock out the machine in accordance with SOP-00087.",
        "Records shall be retained for 3 years.",
    ]
    doc = extractor.extract(make_pdf(pages), max_pages=MAX_PAGES)

    assert doc.page_count == 3
    assert doc.extractor == extractor.name
    assert doc.warnings == []
    for number, (page, expected) in enumerate(zip(doc.pages, pages, strict=True), start=1):
        assert page.number == number
        assert page.text == expected
        assert page.char_count == len(expected)
        assert page.has_text_layer
        assert not page.needs_ocr


def test_markers_never_leak_to_other_pages(extractor: PdfPlumberExtractor) -> None:
    count = 40
    pages = [f"MARKER-{i:03d} " + "filler text for the page body " * 6 for i in range(1, count + 1)]
    doc = extractor.extract(make_pdf(pages), max_pages=MAX_PAGES)

    assert [p.number for p in doc.pages] == list(range(1, count + 1))
    for page in doc.pages:
        found = re.findall(r"MARKER-\d{3}", page.text)
        assert found == [f"MARKER-{page.number:03d}"]


def test_multiline_page_keeps_line_structure(extractor: PdfPlumberExtractor) -> None:
    text = "7.2.1 Read gauge PG-1.\n7.2.2 Record the oil temperature.\n7.2.3 Check the oil level."
    doc = extractor.extract(make_pdf([text]), max_pages=MAX_PAGES)
    assert doc.pages[0].text == text


def test_library_diagnostics_do_not_log_document_content(
    extractor: PdfPlumberExtractor, caplog: pytest.LogCaptureFixture
) -> None:
    # A malformed text operator makes pdfminer log the offending operand verbatim.
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 750, "Visible text on the page.")
    pdf._code.append("BT /F1 12 Tf 72 700 Td /CONFIDENTIAL-OPERAND Tj ET")
    pdf.showPage()
    pdf.save()
    caplog.set_level(logging.DEBUG)

    doc = extractor.extract(buffer.getvalue(), max_pages=MAX_PAGES)

    assert doc.pages[0].text == "Visible text on the page."
    assert not [r for r in caplog.records if "CONFIDENTIAL" in r.getMessage()]


def test_every_page_is_closed_after_extraction(
    extractor: PdfPlumberExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[int] = []
    original_close = Page.close

    def spy_close(self: Page) -> None:
        closed.append(self.page_number)
        original_close(self)

    monkeypatch.setattr(Page, "close", spy_close)
    extractor.extract(make_pdf(["one", "two", "three"]), max_pages=MAX_PAGES)
    assert {1, 2, 3} <= set(closed)


# --- Blank and scanned pages ----------------------------------------------------------------


def test_blank_page_is_not_flagged_for_ocr(extractor: PdfPlumberExtractor) -> None:
    doc = extractor.extract(make_pdf(["First page.", "", "Third page."]), max_pages=MAX_PAGES)

    blank = doc.pages[1]
    assert blank.number == 2
    assert blank.text == ""
    assert blank.char_count == 0
    assert not blank.has_text_layer
    assert not blank.needs_ocr
    assert doc.pages_needing_ocr == []
    assert doc.warnings == ["Page 2 contains no text."]


def test_image_only_page_needs_ocr(extractor: PdfPlumberExtractor) -> None:
    data = make_pdf_with_image_page(["Introduction page with real text.", None, "Closing page."])
    doc = extractor.extract(data, max_pages=MAX_PAGES)

    scanned = doc.pages[1]
    assert scanned.number == 2
    assert scanned.needs_ocr
    assert not scanned.has_text_layer
    assert scanned.char_count == 0
    assert doc.pages[0].text == "Introduction page with real text."
    assert doc.pages[2].text == "Closing page."
    assert doc.pages_needing_ocr == [2]
    assert doc.warnings == [SCANNED_WARNING.format(n=2)]


def test_warnings_group_many_pages(extractor: PdfPlumberExtractor) -> None:
    data = make_pdf_with_image_page(["Text.", "", "", "", "More text.", None, None])
    doc = extractor.extract(data, max_pages=MAX_PAGES)

    assert doc.pages_needing_ocr == [6, 7]
    assert doc.warnings == [
        "Pages 6, 7 have no usable text layer and appear to be scanned images; "
        "OCR is not available in this version.",
        "Pages 2-4 contain no text.",
    ]


@pytest.mark.parametrize(
    ("numbers", "expected"),
    [
        ([3], "3"),
        ([3, 5], "3, 5"),
        ([2, 3], "2, 3"),
        ([2, 3, 4], "2-4"),
        ([9, 2, 3, 4, 7, 10], "2-4, 7, 9, 10"),
        ([1, 2, 3, 5, 6, 7, 8], "1-3, 5-8"),
    ],
)
def test_format_page_numbers(numbers: list[int], expected: str) -> None:
    assert format_page_numbers(numbers) == expected


# --- Rejected inputs ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"Hello, this is plain text and not a PDF document.",
        b"PK\x03\x04\x14\x00\x06\x00",  # ZIP / DOCX
        b"<html><body>%PDF-1.7</body></html>",
        b" " * 1020 + b"%PDF-1.7\n",  # header not within the first 1024 bytes
    ],
    ids=["empty", "text", "zip", "html", "late-header"],
)
def test_non_pdf_bytes_are_unsupported(extractor: PdfPlumberExtractor, data: bytes) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        extractor.extract(data, max_pages=MAX_PAGES)


@pytest.mark.parametrize("prefix", [b"\xef\xbb\xbf", b"\r\n  \t", b"\xef\xbb\xbf\n"])
def test_leading_bom_and_whitespace_are_accepted(
    extractor: PdfPlumberExtractor, prefix: bytes
) -> None:
    data = prefix + make_pdf(["Text after a byte-order mark."])
    assert looks_like_pdf(data)
    doc = extractor.extract(data, max_pages=MAX_PAGES)
    assert doc.pages[0].text == "Text after a byte-order mark."


@pytest.mark.parametrize(
    "data",
    [
        make_pdf(["First page of a document.", "Second page."])[:400],
        b"%PDF-1.4\n" + b"\x00garbage\xff" * 60,
        b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n%%EOF",
    ],
    ids=["truncated", "garbage", "dangling-reference"],
)
def test_corrupt_pdf_raises_extraction_error_without_leaking_details(
    extractor: PdfPlumberExtractor, data: bytes
) -> None:
    with pytest.raises(ExtractionError) as info:
        extractor.extract(data, max_pages=MAX_PAGES)

    error = info.value
    assert type(error) is ExtractionError
    assert error.code == "extraction_failed"
    assert error.message == ExtractionError.default_message
    # The library exception (which may quote document content) is not chained.
    assert error.__cause__ is None
    assert error.__suppress_context__


def test_password_protected_pdf_is_rejected(extractor: PdfPlumberExtractor) -> None:
    data = make_pdf(["Confidential text."], encrypt_password="pw")
    with pytest.raises(EncryptedDocumentError) as info:
        extractor.extract(data, max_pages=MAX_PAGES)
    assert info.value.code == "document_encrypted"
    assert info.value.__cause__ is None


def test_encrypted_pdf_without_user_password_is_rejected(extractor: PdfPlumberExtractor) -> None:
    # Opens without a password (owner-password restrictions only) but is still encrypted.
    data = make_pdf(["Restricted text."], encrypt_password="")
    with pytest.raises(EncryptedDocumentError):
        extractor.extract(data, max_pages=MAX_PAGES)


def test_too_many_pages_is_rejected_with_count_and_limit(extractor: PdfPlumberExtractor) -> None:
    data = make_pdf(["one", "two", "three"])
    with pytest.raises(DocumentTooLargeError) as info:
        extractor.extract(data, max_pages=2)
    assert info.value.code == "document_too_large"
    assert "3 pages" in info.value.message
    assert "2 pages" in info.value.message


def test_page_limit_is_inclusive(extractor: PdfPlumberExtractor) -> None:
    doc = extractor.extract(make_pdf(["one", "two"]), max_pages=2)
    assert doc.page_count == 2


def test_document_without_any_text_is_rejected(extractor: PdfPlumberExtractor) -> None:
    with pytest.raises(NoExtractableTextError):
        extractor.extract(make_pdf(["", ""]), max_pages=MAX_PAGES)


def test_fully_scanned_document_is_rejected(extractor: PdfPlumberExtractor) -> None:
    with pytest.raises(NoExtractableTextError) as info:
        extractor.extract(make_pdf_with_image_page([None, None]), max_pages=MAX_PAGES)
    assert info.value.code == "no_extractable_text"


# --- Normalization --------------------------------------------------------------------------


def test_normalize_removes_control_characters_but_keeps_tabs_and_newlines() -> None:
    raw = "Step\x001\x07 check\tgauge\x0bPG-1\x1f.\nNext line\x0c."
    assert normalize_text(raw) == "Step1 check\tgaugePG-1.\nNext line."


def test_normalize_line_endings_and_trailing_whitespace() -> None:
    raw = "first line   \r\nsecond line\t\rthird line \n"
    assert normalize_text(raw) == "first line\nsecond line\nthird line"


def test_normalize_collapses_runs_of_blank_lines() -> None:
    raw = "a\n\nb\n\n\nc\n\n\n\nd\n  \n \n\t\n\n\n\ne"
    # Up to two blank lines are kept; three or more collapse to two.
    assert normalize_text(raw) == "a\n\nb\n\n\nc\n\n\nd\n\n\ne"


def test_normalize_strips_leading_and_trailing_blank_lines_only() -> None:
    raw = "\n  \n    indented first line\nlast line\n\n \n"
    assert normalize_text(raw) == "    indented first line\nlast line"


def test_normalize_never_alters_words() -> None:
    raw = "pressure-\nreducing valve \u2013 55\u201365 bar, 45 N\u00b7m, 40\u201360 \u00b0C"
    assert normalize_text(raw) == raw


def test_extracted_page_text_is_normalized(
    extractor: PdfPlumberExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = "  \nStep\x00 one  \r\n\n\n\n\nStep two\x07\n"
    monkeypatch.setattr(Page, "extract_text", lambda self, **kwargs: raw)

    doc = extractor.extract(make_pdf(["placeholder text"]), max_pages=MAX_PAGES)

    assert doc.pages[0].text == "Step one\n\n\nStep two"
    assert doc.pages[0].char_count == len("Step one\n\n\nStep two")


# --- OCR hook -------------------------------------------------------------------------------


def test_ocr_engine_fills_scanned_pages() -> None:
    ocr = FakeOcr("Recognized text of page {n}\x00 with enough characters.  ")
    extractor = PdfPlumberExtractor(ocr=ocr)
    data = make_pdf_with_image_page(["Regular text page.", None, ""])

    doc = extractor.extract(data, max_pages=MAX_PAGES)

    assert [number for _, number in ocr.calls] == [2]  # not called for text or blank pages
    assert ocr.calls[0][0] == data
    page = doc.pages[1]
    assert page.text == "Recognized text of page 2 with enough characters."
    assert page.char_count == len(page.text)
    assert not page.has_text_layer
    assert not page.needs_ocr
    assert doc.pages_needing_ocr == []
    assert doc.warnings == [
        "Page 3 contains no text.",
        "Text on page 2 was produced by OCR (fake-ocr 1.0); verify it against the original.",
    ]


def test_ocr_makes_fully_scanned_document_extractable() -> None:
    extractor = PdfPlumberExtractor(ocr=FakeOcr("OCR text for page {n}."))
    doc = extractor.extract(make_pdf_with_image_page([None, None]), max_pages=MAX_PAGES)
    assert [p.text for p in doc.pages] == ["OCR text for page 1.", "OCR text for page 2."]
    assert doc.warnings == [
        "Text on pages 1, 2 was produced by OCR (fake-ocr 1.0); verify it against the original."
    ]


def test_ocr_without_result_keeps_page_flagged() -> None:
    extractor = PdfPlumberExtractor(ocr=FakeOcr("  \n"))
    doc = extractor.extract(make_pdf_with_image_page(["Text page.", None]), max_pages=MAX_PAGES)
    assert doc.pages[1].needs_ocr
    assert doc.warnings == [
        "Page 2 has no usable text layer and appears to be a scanned image; "
        "OCR did not recognize any text."
    ]


def test_ocr_failure_raises_extraction_error() -> None:
    extractor = PdfPlumberExtractor(ocr=FakeOcr(RuntimeError("engine crashed: secret detail")))
    with pytest.raises(ExtractionError) as info:
        extractor.extract(make_pdf_with_image_page(["Text page.", None]), max_pages=MAX_PAGES)
    assert info.value.message == "OCR failed on page 2."
    assert info.value.__cause__ is None
