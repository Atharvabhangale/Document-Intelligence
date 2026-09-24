"""Document context builder and size guards.

The document context is the large, stable part of every LLM request: document metadata for
orientation plus the page-tagged extracted text. It is byte-identical across tasks for the same
document so providers can cache it (e.g. Anthropic prompt caching)::

    <document_metadata note="...">SOP-00123 / Maintenance SOP / A.3 / Released</document_metadata>
    <document page_count="2">
    <page number="1">...text...</page>
    <page number="2" status="no-text">[No extractable text on this page]</page>
    </document>

(the metadata note reads "For orientation only. Do not cite metadata.").

Page text is inserted verbatim except for tag-like sequences (``<page``, ``</page``,
``<document``, ``</document``) whose ``<`` is replaced by U+2039 (single left-pointing angle
quotation mark) so document content cannot close or open a page container. Citation
verification always runs against the original page text.
"""

from __future__ import annotations

import math
import re

from docintel.core.errors import DocumentTooLargeError, NoExtractableTextError
from docintel.core.models import DocumentMetadata, ExtractedDocument

NO_TEXT_PLACEHOLDER = "[No extractable text on this page]"
METADATA_NOTE = "For orientation only. Do not cite metadata."
#: Conservative characters-per-token ratio used for size estimates (real ratios are ~3.5-4.5
#: for English prose; lower means we over-estimate, which is the safe direction).
CHARS_PER_TOKEN = 3.2
#: Replacement for ``<`` in neutralized tag-like sequences (U+2039 SINGLE LEFT-POINTING ANGLE
#: QUOTATION MARK).
TAG_ESCAPE = "\u2039"

# "<" that starts something that looks like a page/document container tag, tolerating
# whitespace ("< /page", "</ document") and matching case-insensitively.
_CONTAINER_TAG_RE = re.compile(r"<(?=\s*/?\s*(?:page|document))", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def neutralize_tags(text: str, pattern: re.Pattern[str] = _CONTAINER_TAG_RE) -> str:
    """Replace the ``<`` of every tag-like sequence matched by ``pattern`` with U+2039."""
    return pattern.sub(TAG_ESCAPE, text)


def build_document_context(metadata: DocumentMetadata, extracted: ExtractedDocument) -> str:
    """Return the page-tagged document context (deterministic, byte-stable)."""
    lines = [
        f'<document_metadata note="{METADATA_NOTE}">{_metadata_line(metadata)}</document_metadata>',
        f'<document page_count="{extracted.page_count}">',
    ]
    for page in extracted.pages:
        if page.text.strip():
            lines.append(f'<page number="{page.number}">{neutralize_tags(page.text)}</page>')
        else:
            lines.append(
                f'<page number="{page.number}" status="no-text">{NO_TEXT_PLACEHOLDER}</page>'
            )
    lines.append("</document>")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: ``ceil(len(text) / 3.2)``."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def ensure_analyzable(
    extracted: ExtractedDocument, context: str, *, max_document_tokens: int
) -> int:
    """Check that a document can be analyzed in a single request.

    Returns the estimated token count of ``context``.

    Raises:
        NoExtractableTextError: the document has no extracted text at all.
        DocumentTooLargeError: the estimated size of ``context`` exceeds the limit.
    """
    if extracted.total_chars == 0 or not any(page.text.strip() for page in extracted.pages):
        raise NoExtractableTextError()
    estimated = estimate_tokens(context)
    if estimated > max_document_tokens:
        raise DocumentTooLargeError(
            f"The document is too large to analyze in a single request (about {estimated:,} "
            f"tokens; the limit is {max_document_tokens:,}). Analyzing large documents in "
            "sections is not available in this version.",
            details={"estimatedTokens": estimated, "maxDocumentTokens": max_document_tokens},
        )
    return estimated


def _metadata_line(metadata: DocumentMetadata) -> str:
    """``number / name / revision.iteration / state / document type`` (known values only)."""
    values = (
        metadata.number,
        metadata.name,
        metadata.version_label,
        metadata.state,
        metadata.document_type,
    )
    parts = [_clean_metadata_value(value) for value in values if value]
    # Metadata is never cited, so every "<" can be neutralized, not only container tags.
    return " / ".join(part for part in parts if part).replace("<", TAG_ESCAPE)


def _clean_metadata_value(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()
