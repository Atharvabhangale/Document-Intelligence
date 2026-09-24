"""Citation verification.

The model cites its sources as ``{page, quote}`` pairs. ``CitationVerifier`` checks each quote
against the *original* extracted page text (not the model's view of it):

1. exact match of the normalized quote on the cited page -> ``verified``;
2. exact match on another page -> ``relocated``;
3. quotes with ellipses: every fragment found in order on one page -> ``verified``/``relocated``;
4. fuzzy match (``difflib``) of word windows, cited page first, ratio >= 0.88 -> ``approximate``;
5. otherwise ``invalid_page`` when the cited page does not exist, else ``unverified``.

Normalization makes matching robust to extraction and typography differences (Unicode
compatibility forms and ligatures, curly quotes, dash variants, soft hyphens, zero-width
characters, line-break hyphenation, whitespace and case) without changing what is displayed.

``CitationRegistry`` deduplicates citations across a report and assigns ids ``C1``, ``C2``, ...
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import accumulate

from docintel.core.models import ExtractedDocument
from docintel.schemas.report import Citation, CitationStatus, SourceQuote

#: Minimum fuzzy ratio for an ``approximate`` match.
APPROXIMATE_THRESHOLD = 0.88
#: Quotes with fewer words are only accepted on an exact match.
MIN_MATCH_WORDS = 3
#: Quotes with more words are not fuzzy-matched (the prompt asks for 5-25 words).
MAX_FUZZY_WORDS = 60

# Fuzzy search effort limits (per quote).
_WINDOW_SLACK = 0.2  # window lengths of quote length +-20 %
_MIN_WORD_OVERLAP = 0.5  # share of quote words a candidate region must contain
_MAX_ANCHORS_PER_PAGE = 3
_MAX_ANCHORS = 8  # candidate regions examined per scan (cited page / other pages)
_WINDOWS_PER_ANCHOR = 4  # windows per region compared with SequenceMatcher

_CHAR_MAP = str.maketrans(
    {
        # single quotes and primes
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        # double quotes and double primes
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2033": '"',
        # hyphens, dashes and minus
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        # the document context escapes "<" of tag-like sequences as U+2039
        "\u2039": "<",
        # invisible characters
        "\u00ad": None,
        "\u200b": None,
        "\u200c": None,
        "\u200d": None,
        "\u2060": None,
        "\ufeff": None,
    }
)
_SOFT_HYPHEN_BREAK_RE = re.compile(r"\u00ad[ \t]*\r?\n[ \t]*")
_HYPHEN_BREAK_RE = re.compile(r"(\w)-[ \t]*\r?\n[ \t]*(\w)")
_WHITESPACE_RE = re.compile(r"\s+")
# Ellipses: "..." (NFKC turns U+2026 HORIZONTAL ELLIPSIS into "..."), also spaced ". . ."
_ELLIPSIS_RE = re.compile(r"\s*\.(?:\s?\.){2,}\s*")
_EDGE_PUNCTUATION = " \"'`.,;:!?()[]{}<>\u00ab\u00bb*-\u2022"


@dataclass(frozen=True)
class CitationMatch:
    status: CitationStatus
    matched_page: int | None
    score: float


@dataclass(frozen=True)
class _Page:
    number: int
    text: str  # normalized, line-break hyphenation joined ("main-\ntenance" -> "maintenance")
    alt_text: str | None  # normalized, hyphen kept ("pre-\nstart" -> "pre-start"), if different
    words: tuple[str, ...]
    keys: tuple[str, ...]  # words without edge punctuation, for overlap counting
    key_set: frozenset[str]


def normalize(text: str, *, join_hyphenation: bool = True) -> str:
    """Normalize text for matching (never for display).

    NFKC, unified quotes and dashes, invisible characters removed, line-break hyphenation
    joined (or, with ``join_hyphenation=False``, the line break removed and the hyphen kept),
    whitespace collapsed, casefolded and stripped.
    """
    text = _SOFT_HYPHEN_BREAK_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text.translate(_CHAR_MAP)).translate(_CHAR_MAP)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2" if join_hyphenation else r"\1-\2", text)
    return _WHITESPACE_RE.sub(" ", text).casefold().strip()


def normalize_quote(quote: str) -> str:
    """``normalize`` plus stripping of surrounding quotes, brackets and punctuation."""
    return normalize(quote).strip(_EDGE_PUNCTUATION)


class CitationVerifier:
    """Verifies quotes against the extracted text of one document.

    Page text is normalized once at construction; instances are cheap to query and hold no
    mutable state, so one verifier can serve a whole report.
    """

    def __init__(self, extracted: ExtractedDocument) -> None:
        self._page_count = extracted.page_count
        self._pages: dict[int, _Page] = {}
        for page in extracted.pages:
            joined = normalize(page.text)
            kept = normalize(page.text, join_hyphenation=False)
            words = tuple(joined.split(" ")) if joined else ()
            keys = tuple(word.strip(_EDGE_PUNCTUATION) for word in words)
            self._pages[page.number] = _Page(
                number=page.number,
                text=joined,
                alt_text=kept if kept != joined else None,
                words=words,
                keys=keys,
                key_set=frozenset(keys),
            )

    def verify(self, page: int, quote: str) -> CitationMatch:
        """Verify that ``quote`` appears on ``page`` (1-based) of the document."""
        page_exists = 1 <= page <= self._page_count and page in self._pages
        normalized = normalize_quote(quote)
        if not normalized:
            return CitationMatch("invalid_page" if not page_exists else "unverified", None, 0.0)

        found = self._find(page, lambda text: normalized in text)
        if found is not None:
            return self._exact_result(page, found)

        fragments = _fragments(normalized)
        if fragments:
            found = self._find(page, lambda text: _contains_in_order(fragments, text))
            if found is not None:
                return self._exact_result(page, found)

        best_ratio, best_page = 0.0, None
        fuzzy_text = " ".join(fragments) if fragments else normalized
        word_count = len(fuzzy_text.split(" "))
        if MIN_MATCH_WORDS <= word_count <= MAX_FUZZY_WORDS:
            best_ratio, best_page = self._fuzzy_search(fuzzy_text, page)
        score = round(best_ratio, 3)
        if best_page is not None and score >= APPROXIMATE_THRESHOLD:
            return CitationMatch("approximate", best_page, score)
        return CitationMatch("unverified" if page_exists else "invalid_page", None, score)

    # --- exact matching ----------------------------------------------------------------------

    def _pages_cited_first(self, page: int) -> Iterator[_Page]:
        cited = self._pages.get(page)
        if cited is not None:
            yield cited
        for candidate in self._pages.values():
            if candidate.number != page:
                yield candidate

    def _find(self, page: int, predicate: Callable[[str], bool]) -> int | None:
        """Number of the first page (cited page first) whose text satisfies ``predicate``."""
        for candidate in self._pages_cited_first(page):
            if predicate(candidate.text) or (
                candidate.alt_text is not None and predicate(candidate.alt_text)
            ):
                return candidate.number
        return None

    @staticmethod
    def _exact_result(cited: int, found: int) -> CitationMatch:
        status: CitationStatus = "verified" if found == cited else "relocated"
        return CitationMatch(status, found, 1.0)

    # --- fuzzy matching ----------------------------------------------------------------------

    def _fuzzy_search(self, quote: str, page: int) -> tuple[float, int | None]:
        """Best fuzzy ratio: cited page first, then the other pages if still below threshold."""
        search = _FuzzySearch(quote)
        cited = self._pages.get(page)
        if cited is not None:
            search.scan([cited])
            if search.best_ratio >= APPROXIMATE_THRESHOLD:
                return search.best_ratio, search.best_page
        search.scan([candidate for candidate in self._pages.values() if candidate.number != page])
        return search.best_ratio, search.best_page


class _FuzzySearch:
    """Bounded search for the word window most similar to a quote.

    1. Pages sharing too few distinct words with the quote are skipped.
    2. Candidate regions ("anchors") are quote-length word windows ranked by how many of their
       words occur in the quote (sliding window over prefix sums, O(1) per window).
    3. Around the best anchors, windows of the quote's length +-20 % are ranked the same way and
       only the best few are compared character by character with ``SequenceMatcher``.

    Effort per scan is therefore bounded by ``_MAX_ANCHORS * _WINDOWS_PER_ANCHOR`` ratio
    computations regardless of document size.
    """

    def __init__(self, quote: str) -> None:
        words = quote.split(" ")
        self._n = len(words)
        self._slack = max(1, math.ceil(self._n * _WINDOW_SLACK))
        self._widths = range(max(1, self._n - self._slack), self._n + self._slack + 1)
        keys = (word.strip(_EDGE_PUNCTUATION) for word in words)
        self._keys = frozenset(key for key in keys if key)
        self._min_overlap = max(1, math.ceil(self._n * _MIN_WORD_OVERLAP))
        self._min_distinct = max(1, math.ceil(len(self._keys) * _MIN_WORD_OVERLAP))
        self._matcher = SequenceMatcher(None, autojunk=False)
        self._matcher.set_seq2(quote)
        self.best_ratio = 0.0
        self.best_page: int | None = None

    def scan(self, pages: Iterable[_Page]) -> None:
        anchors: list[tuple[int, int, int, _Page, list[int]]] = []
        for order, page in enumerate(pages):
            if not page.words or len(self._keys & page.key_set) < self._min_distinct:
                continue
            prefix = [0, *accumulate(key in self._keys for key in page.keys)]
            for overlap, start in self._page_anchors(prefix):
                anchors.append((overlap, order, start, page, prefix))
        anchors.sort(key=lambda item: (-item[0], item[1], item[2]))

        seen: set[tuple[int, int, int]] = set()
        for _, _, anchor, page, prefix in anchors[:_MAX_ANCHORS]:
            for start, width in self._best_windows(prefix, anchor):
                if (page.number, start, width) in seen:
                    continue
                seen.add((page.number, start, width))
                self._evaluate(" ".join(page.words[start : start + width]), page.number)
                if self.best_ratio >= 1.0:
                    return

    def _page_anchors(self, prefix: list[int]) -> list[tuple[int, int]]:
        """Best non-overlapping quote-length windows of a page as ``(overlap, start)``."""
        length = len(prefix) - 1
        span = min(self._n, length)
        threshold = min(self._min_overlap, span)
        scored = [
            (prefix[i + span] - prefix[i], i)
            for i in range(length - span + 1)
            if prefix[i + span] - prefix[i] >= threshold
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        anchors: list[tuple[int, int]] = []
        for overlap, start in scored:
            if all(abs(start - other) >= span for _, other in anchors):
                anchors.append((overlap, start))
                if len(anchors) >= _MAX_ANCHORS_PER_PAGE:
                    break
        return anchors

    def _best_windows(self, prefix: list[int], anchor: int) -> list[tuple[int, int]]:
        """The most promising ``(start, width)`` windows near ``anchor`` by word overlap."""
        length = len(prefix) - 1
        scored: list[tuple[float, int, int, int, int]] = []
        for start in range(max(0, anchor - self._slack), min(anchor + self._slack, length - 1) + 1):
            for width in self._widths:
                end = start + width
                if end > length:
                    break
                dice = 2 * (prefix[end] - prefix[start]) / (width + self._n)
                scored.append((dice, -abs(width - self._n), -abs(start - anchor), start, width))
        scored.sort(reverse=True)
        return [(start, width) for *_, start, width in scored[:_WINDOWS_PER_ANCHOR]]

    def _evaluate(self, candidate: str, page_number: int) -> None:
        matcher, best = self._matcher, self.best_ratio
        matcher.set_seq1(candidate)
        # Cheap upper bounds first; only a potential improvement pays for the full ratio.
        if matcher.real_quick_ratio() <= best or matcher.quick_ratio() <= best:
            return
        ratio = matcher.ratio()
        if ratio > self.best_ratio:
            self.best_ratio = ratio
            self.best_page = page_number


class CitationRegistry:
    """Collects the citations of one report, deduplicated by (page, normalized quote).

    Ids are assigned in first-seen order: ``C1``, ``C2``, ...
    """

    def __init__(self, verifier: CitationVerifier) -> None:
        self._verifier = verifier
        self._by_key: dict[tuple[int, str], Citation] = {}
        self._by_id: dict[str, Citation] = {}

    def register(self, sources: Iterable[SourceQuote]) -> list[str]:
        """Verify and register ``sources``; return their citation ids (unique, in order).

        Sources with an empty quote carry no evidence and are skipped.
        """
        ids: list[str] = []
        for source in sources:
            quote = source.quote.strip()
            if not quote:
                continue
            key = (source.page, normalize_quote(quote))
            citation = self._by_key.get(key)
            if citation is None:
                match = self._verifier.verify(source.page, quote)
                citation = Citation(
                    id=f"C{len(self._by_id) + 1}",
                    page=source.page,
                    quote=quote,
                    status=match.status,
                    matched_page=match.matched_page,
                    match_score=match.score,
                )
                self._by_key[key] = citation
                self._by_id[citation.id] = citation
            if citation.id not in ids:
                ids.append(citation.id)
        return ids

    @property
    def citations(self) -> list[Citation]:
        """All registered citations in id order."""
        return list(self._by_id.values())

    def status(self, citation_id: str) -> CitationStatus:
        return self._by_id[citation_id].status


def _fragments(normalized_quote: str) -> list[str]:
    """Fragments of a quote with inner ellipses, or ``[]`` when the rule does not apply.

    Applies when there are at least two fragments and at least one has ``MIN_MATCH_WORDS``
    words; every fragment must then be found, in order, on one page.
    """
    parts = [part.strip(_EDGE_PUNCTUATION) for part in _ELLIPSIS_RE.split(normalized_quote)]
    fragments = [part for part in parts if part]
    if len(fragments) < 2 or not any(len(f.split(" ")) >= MIN_MATCH_WORDS for f in fragments):
        return []
    return fragments


def _contains_in_order(fragments: list[str], text: str) -> bool:
    position = 0
    for fragment in fragments:
        index = text.find(fragment, position)
        if index < 0:
            return False
        position = index + len(fragment)
    return True
