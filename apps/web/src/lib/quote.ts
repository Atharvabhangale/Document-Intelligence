/**
 * Locating a cited quote inside extracted page text, for highlighting.
 *
 * Mirrors the normalization of the backend's citation verifier
 * (apps/api/src/docintel/intelligence/citations.py) so that a quote the backend marked as
 * verified can be found here too: Unicode compatibility forms (NFKC, ligatures), curly quotes,
 * dash variants, invisible characters, line-break hyphenation, whitespace and case are ignored,
 * and quotes containing ellipses match when their fragments appear in order. Unlike the
 * backend, every normalized character keeps a pointer to its position in the original text so
 * the match can be mapped back to original string offsets.
 */

export interface TextRange {
  /** Start offset in the original string (UTF-16 code units, inclusive). */
  start: number;
  /** End offset in the original string (exclusive). */
  end: number;
}

const CHAR_MAP: Readonly<Record<string, string>> = {
  "‘": "'",
  "’": "'",
  "‚": "'",
  "‛": "'",
  "′": "'",
  "“": '"',
  "”": '"',
  "„": '"',
  "‟": '"',
  "″": '"',
  "‐": "-",
  "‑": "-",
  "‒": "-",
  "–": "-",
  "—": "-",
  "―": "-",
  "−": "-",
  "‹": "<",
};
const INVISIBLE = new Set(["­", "​", "‌", "‍", "⁠", "﻿"]);
const EDGE_PUNCTUATION = new Set([..." \"'`.,;:!?()[]{}<>«»*-•"]);
const ELLIPSIS_RE = /\s*\.(?:\s?\.){2,}\s*/;
const WORD_RE = /[\p{L}\p{N}_]/u;
const LINE_BREAK_RE = /^[ \t]*\r?\n[ \t]*/;

interface NormalizedText {
  text: string;
  /** Original start offset of each normalized character. */
  starts: number[];
  /** Original end offset of each normalized character. */
  ends: number[];
}

function mapChar(ch: string): string {
  const mapped = CHAR_MAP[ch] ?? ch;
  return [...mapped.normalize("NFKC")]
    .map((c) => CHAR_MAP[c] ?? c)
    .join("")
    .toLowerCase();
}

/**
 * Normalize `source`, recording original offsets.
 *
 * @param joinHyphenation "main-\ntenance" -> "maintenance" when true; "pre-\nstart" ->
 *   "pre-start" when false (both variants are tried, as in the backend).
 */
function normalizeWithOffsets(source: string, joinHyphenation: boolean): NormalizedText {
  const out: NormalizedText = { text: "", starts: [], ends: [] };
  const chars: string[] = [];
  let pendingSpace: TextRange | null = null;

  const emit = (value: string, start: number, end: number) => {
    for (const c of value) {
      if (/\s/.test(c)) {
        if (chars.length > 0) pendingSpace ??= { start, end };
        continue;
      }
      if (pendingSpace) {
        chars.push(" ");
        out.starts.push(pendingSpace.start);
        out.ends.push(pendingSpace.end);
        pendingSpace = null;
      }
      chars.push(c);
      out.starts.push(start);
      out.ends.push(end);
    }
  };

  let i = 0;
  while (i < source.length) {
    const codePoint = source.codePointAt(i) ?? 0;
    const ch = String.fromCodePoint(codePoint);
    const next = i + ch.length;

    if (ch === "­") {
      // Soft hyphen at a line break joins the word; elsewhere it is invisible.
      const lineBreak = LINE_BREAK_RE.exec(source.slice(next));
      i = next + (lineBreak ? lineBreak[0].length : 0);
      continue;
    }
    if (INVISIBLE.has(ch)) {
      i = next;
      continue;
    }

    const mapped = mapChar(ch);
    if (mapped === "-") {
      const previous = chars.at(-1);
      const lineBreak = LINE_BREAK_RE.exec(source.slice(next));
      const following = lineBreak ? source.slice(next + lineBreak[0].length).charAt(0) : "";
      if (
        lineBreak &&
        pendingSpace === null &&
        previous !== undefined &&
        WORD_RE.test(previous) &&
        WORD_RE.test(following)
      ) {
        if (!joinHyphenation) emit("-", i, next);
        i = next + lineBreak[0].length;
        continue;
      }
    }

    emit(mapped, i, next);
    i = next;
  }
  out.text = chars.join("");
  return out;
}

function stripEdges(value: string): string {
  const chars = [...value];
  let start = 0;
  let end = chars.length;
  while (start < end && EDGE_PUNCTUATION.has(chars[start] ?? "")) start += 1;
  while (end > start && EDGE_PUNCTUATION.has(chars[end - 1] ?? "")) end -= 1;
  return chars.slice(start, end).join("");
}

/** Normalized, non-empty fragments of a quote (split at ellipses). */
function quoteFragments(quote: string): string[] {
  const normalized = normalizeWithOffsets(quote, true).text;
  return normalized
    .split(ELLIPSIS_RE)
    .map(stripEdges)
    .filter((fragment) => fragment.length > 0);
}

function searchFragments(page: NormalizedText, fragments: readonly string[]): TextRange | null {
  let from = 0;
  let first: number | null = null;
  let lastEnd = 0;
  for (const fragment of fragments) {
    const index = page.text.indexOf(fragment, from);
    if (index < 0) return null;
    first ??= index;
    lastEnd = index + fragment.length;
    from = lastEnd;
  }
  if (first === null) return null;
  const start = page.starts[first];
  const end = page.ends[lastEnd - 1];
  return start === undefined || end === undefined ? null : { start, end };
}

/**
 * Find `quote` in `pageText`, ignoring case, whitespace differences, curly vs straight quotes,
 * dash variants, ligatures and line-break hyphenation.
 *
 * @returns the range in `pageText` (original offsets) or `null` when the quote is not on the
 *   page. For quotes with ellipses the range spans from the first to the last fragment.
 */
export function findQuoteRange(pageText: string, quote: string): TextRange | null {
  const fragments = quoteFragments(quote);
  if (fragments.length === 0 || pageText.length === 0) return null;
  for (const join of [true, false]) {
    const range = searchFragments(normalizeWithOffsets(pageText, join), fragments);
    if (range) return range;
  }
  return null;
}
