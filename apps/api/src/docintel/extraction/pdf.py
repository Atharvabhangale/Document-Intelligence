"""Page-aware PDF text extraction with pdfplumber.

``PdfPlumberExtractor`` turns PDF bytes into an ``ExtractedDocument`` whose page N is physical
page N of the PDF. Text is normalized only in ways that cannot change words (control characters,
line endings, trailing whitespace, runs of blank lines) so that citations can quote it verbatim.

Pages without a usable text layer that contain images are flagged ``needs_ocr``. OCR is not
available in this version; an ``OcrEngine`` can be passed to the extractor to fill those pages
later.

Security: exception messages from the PDF libraries can contain fragments of the document, so
they are never propagated to error messages or logs — only the exception type name is logged.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError

from docintel.core.errors import (
    DocIntelError,
    DocumentTooLargeError,
    EncryptedDocumentError,
    ExtractionError,
    NoExtractableTextError,
    UnsupportedMediaTypeError,
)
from docintel.core.models import ExtractedDocument, ExtractedPage
from docintel.extraction.base import OcrEngine, TextExtractor

logger = logging.getLogger(__name__)

# pdfminer/pdfplumber diagnostics quote PDF internals verbatim (content-stream operands, parser
# stacks, metadata values), which can include document text - even at ERROR level. Silence them;
# failures are still reported through this module's logger, by exception type only.
for _library in ("pdfminer", "pdfplumber"):
    logging.getLogger(_library).setLevel(logging.CRITICAL)

# A page with fewer characters than this that contains images looks like a scanned page.
OCR_CHAR_THRESHOLD = 25

# PDF readers accept the "%PDF-" header anywhere in the first 1024 bytes; we additionally
# require that only whitespace (or a UTF-8 BOM) precedes it.
_PDF_MAGIC = b"%PDF-"
_HEADER_WINDOW = 1024
_UTF8_BOM = b"\xef\xbb\xbf"
_PDF_WHITESPACE = b"\x00\t\n\x0c\r "

# C0 control characters except TAB (0x09) and LF (0x0a). CR is converted to LF beforehand.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f]")
# Four or more newlines == three or more consecutive blank lines.
_EXCESS_BLANK_LINES = re.compile(r"\n{4,}")


def normalize_text(text: str) -> str:
    """Normalize extracted page text without altering words.

    Removes C0 control characters (except newline and tab), converts CRLF/CR line endings to LF,
    strips trailing whitespace from each line, collapses three or more consecutive blank lines
    to two and removes leading/trailing blank lines. Words are never changed (no
    dehyphenation), so quotes taken from the result match the document.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _EXCESS_BLANK_LINES.sub("\n\n\n", text)
    return text.strip("\n")


def looks_like_pdf(data: bytes) -> bool:
    """True when ``data`` starts with a PDF header (after optional BOM/whitespace)."""
    head = data[:_HEADER_WINDOW]
    if head.startswith(_UTF8_BOM):
        head = head[len(_UTF8_BOM) :]
    return head.lstrip(_PDF_WHITESPACE).startswith(_PDF_MAGIC)


@dataclass
class _PageResult:
    text: str
    has_text_layer: bool
    needs_ocr: bool


class PdfPlumberExtractor(TextExtractor):
    """Extract page-aware text from PDFs using pdfplumber (pdfminer.six).

    Encrypted PDFs are always rejected, including PDFs that open without a password but carry
    owner-password restrictions: V1 does not interpret PDF permission flags.
    """

    name = f"pdfplumber {pdfplumber.__version__}"

    def __init__(self, ocr: OcrEngine | None = None) -> None:
        self._ocr = ocr

    def extract(self, data: bytes, *, max_pages: int) -> ExtractedDocument:
        if not looks_like_pdf(data):
            raise UnsupportedMediaTypeError()

        try:
            results = self._read_pages(data, max_pages=max_pages)
        except DocIntelError:
            raise
        except Exception as exc:
            # Never chain or log the library exception: its message may quote document content.
            if _is_encryption_error(exc):
                raise EncryptedDocumentError() from None
            logger.info("PDF could not be parsed (%s)", type(exc).__name__)
            raise ExtractionError() from None

        ocr_pages = _apply_ocr(self._ocr, data, results) if self._ocr is not None else []

        pages = [
            ExtractedPage(
                number=number,
                text=result.text,
                char_count=len(result.text),
                has_text_layer=result.has_text_layer,
                needs_ocr=result.needs_ocr,
            )
            for number, result in enumerate(results, start=1)
        ]
        document = ExtractedDocument(
            page_count=len(pages),
            pages=pages,
            extractor=self.name,
            warnings=_warnings(pages, ocr_pages, ocr_name=self._ocr.name if self._ocr else None),
        )
        if document.total_chars == 0:
            raise NoExtractableTextError()
        return document

    def _read_pages(self, data: bytes, *, max_pages: int) -> list[_PageResult]:
        """Extract every page in order, releasing each page's parsed objects when done."""
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            # pdfminer decrypts PDFs that have an empty user password without complaint.
            if getattr(pdf.doc, "encryption", None) is not None:
                raise EncryptedDocumentError()

            page_count = len(pdf.pages)
            if page_count > max_pages:
                raise DocumentTooLargeError(
                    f"The document has {page_count} pages; this version supports at most "
                    f"{max_pages} pages."
                )

            results: list[_PageResult] = []
            for page in pdf.pages:
                try:
                    has_text_layer = bool(page.chars)
                    text = normalize_text(page.extract_text() or "") if has_text_layer else ""
                    results.append(
                        _PageResult(
                            text=text,
                            has_text_layer=has_text_layer,
                            # Little or no text but an image: looks like a scanned page.
                            needs_ocr=len(text) < OCR_CHAR_THRESHOLD and bool(page.images),
                        )
                    )
                finally:
                    page.close()
            return results


def _apply_ocr(ocr: OcrEngine, data: bytes, results: list[_PageResult]) -> list[int]:
    """Fill pages that need OCR with the engine's text; return the page numbers filled.

    Pages for which the engine recognizes no text keep ``needs_ocr``.
    """
    filled: list[int] = []
    for number, result in enumerate(results, start=1):
        if not result.needs_ocr:
            continue
        try:
            text = normalize_text(ocr.ocr_page(data, number))
        except DocIntelError:
            raise
        except Exception as exc:
            logger.info("OCR failed on page %d (%s)", number, type(exc).__name__)
            raise ExtractionError(f"OCR failed on page {number}.") from None
        if text:
            result.text = text
            result.has_text_layer = False
            result.needs_ocr = False
            filled.append(number)
    return filled


def _warnings(
    pages: list[ExtractedPage], ocr_pages: list[int], *, ocr_name: str | None
) -> list[str]:
    """User-safe warnings about scanned, blank and OCR-filled pages."""
    warnings: list[str] = []

    scanned = [p.number for p in pages if p.needs_ocr]
    if scanned:
        reason = (
            "OCR is not available in this version."
            if ocr_name is None
            else "OCR did not recognize any text."
        )
        if len(scanned) == 1:
            warnings.append(
                f"Page {scanned[0]} has no usable text layer and appears to be a scanned "
                f"image; {reason}"
            )
        else:
            warnings.append(
                f"Pages {format_page_numbers(scanned)} have no usable text layer and appear "
                f"to be scanned images; {reason}"
            )

    blank = [p.number for p in pages if p.char_count == 0 and not p.needs_ocr]
    if len(blank) == 1:
        warnings.append(f"Page {blank[0]} contains no text.")
    elif blank:
        warnings.append(f"Pages {format_page_numbers(blank)} contain no text.")

    if ocr_pages:
        label = "page" if len(ocr_pages) == 1 else "pages"
        warnings.append(
            f"Text on {label} {format_page_numbers(ocr_pages)} was produced by OCR "
            f"({ocr_name}); verify it against the original."
        )
    return warnings


def format_page_numbers(numbers: Iterable[int]) -> str:
    """Format sorted page numbers compactly: ``[2, 3, 4, 7, 9, 10]`` -> ``"2-4, 7, 9, 10"``.

    Runs of three or more consecutive pages become a range.
    """
    ordered = sorted(set(numbers))
    parts: list[str] = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{ordered[i]}-{ordered[j]}")
        else:
            parts.extend(str(n) for n in ordered[i : j + 1])
        i = j + 1
    return ", ".join(parts)


def _is_encryption_error(exc: BaseException) -> bool:
    """True if ``exc`` is, wraps or was caused by a pdfminer encryption error.

    pdfplumber wraps pdfminer errors in ``PdfminerException(original)``, so the original is
    found in ``args``; ``__cause__``/``__context__`` are followed as well.
    """
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, PDFEncryptionError):
            return True
        pending.extend(arg for arg in current.args if isinstance(arg, BaseException))
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return False


def get_default_extractor() -> TextExtractor:
    """The extractor used by the application (no OCR in this version)."""
    return PdfPlumberExtractor()
