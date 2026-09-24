"""Page-aware text extraction from document content."""

from docintel.extraction.base import OcrEngine, TextExtractor
from docintel.extraction.pdf import PdfPlumberExtractor, get_default_extractor, normalize_text

__all__ = [
    "OcrEngine",
    "PdfPlumberExtractor",
    "TextExtractor",
    "get_default_extractor",
    "normalize_text",
]
