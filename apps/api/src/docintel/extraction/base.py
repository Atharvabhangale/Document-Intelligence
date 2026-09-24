"""Text extraction abstraction.

Extractors turn document bytes into page-aware text (``ExtractedDocument``). Page boundaries
are preserved: page N of the result is physical page N of the PDF (1-based).

OCR is not implemented in this version. Pages without a usable text layer are flagged with
``needs_ocr=True``; an ``OcrEngine`` can later be plugged into the extractor to fill them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from docintel.core.models import ExtractedDocument


class OcrEngine(ABC):
    """Future OCR fallback for pages without a text layer (not implemented in V1)."""

    name: str

    @abstractmethod
    def ocr_page(self, pdf_bytes: bytes, page_number: int) -> str:
        """Return recognized text for 1-based ``page_number``."""


class TextExtractor(ABC):
    name: str  # e.g. "pdfplumber 0.11.10"

    @abstractmethod
    def extract(self, data: bytes, *, max_pages: int) -> ExtractedDocument:
        """Extract page-aware text.

        Raises:
            UnsupportedMediaTypeError: data is not a PDF.
            EncryptedDocumentError: the PDF is encrypted / password protected.
            DocumentTooLargeError: the PDF has more than ``max_pages`` pages.
            ExtractionError: the PDF is corrupt or cannot be parsed.
        """
