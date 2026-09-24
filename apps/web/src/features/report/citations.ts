/** Citation helpers shared by chips, the Sources section and the source viewer. */
import type { Citation, CitationStatus } from "../../api/types";
import type { Tone } from "../../components/ui/Badge";

export interface CitationStatusMeta {
  label: string;
  /** One-sentence explanation for users. */
  description: string;
  tone: Tone;
}

export const CITATION_STATUS: Readonly<Record<CitationStatus, CitationStatusMeta>> = {
  verified: {
    label: "Verified",
    description: "The quote was found on the cited page.",
    tone: "success",
  },
  relocated: {
    label: "Relocated",
    description: "The quote was found in the document, but on a different page than cited.",
    tone: "info",
  },
  approximate: {
    label: "Approximate",
    description: "Only a close, not exact, match of the quote was found in the document.",
    tone: "warning",
  },
  unverified: {
    label: "Unverified",
    description: "The quote could not be found in the document text.",
    tone: "danger",
  },
  invalid_page: {
    label: "Invalid page",
    description: "The cited page does not exist and the quote was not found elsewhere.",
    tone: "danger",
  },
};

/** Statuses for which the document text supports the quote. */
export function isSupported(status: CitationStatus): boolean {
  return status === "verified" || status === "relocated";
}

/** The page where the evidence is: the matched page when it was found elsewhere. */
export function displayPage(citation: Citation): number {
  if (citation.status === "relocated" || citation.status === "approximate") {
    return citation.matchedPage ?? citation.page;
  }
  return citation.page;
}

export type CitationIndex = ReadonlyMap<string, Citation>;

export function indexCitations(citations: readonly Citation[]): CitationIndex {
  return new Map(citations.map((citation) => [citation.id, citation]));
}

/** Citations for ids, in the given order, skipping unknown ids. */
export function resolveCitations(ids: readonly string[], index: CitationIndex): Citation[] {
  return ids.flatMap((id) => {
    const citation = index.get(id);
    return citation ? [citation] : [];
  });
}

/** Sorted unique pages of the given citations ("where to look"). */
export function citationPages(citations: readonly Citation[]): number[] {
  return [...new Set(citations.map(displayPage))].sort((a, b) => a - b);
}

/** Accessible label, e.g. "Source: page 4, verified". */
export function citationLabel(citation: Citation): string {
  const status = CITATION_STATUS[citation.status].label.toLowerCase();
  const page = displayPage(citation);
  if (page !== citation.page) {
    return `Source: page ${page}, ${status} (cited as page ${citation.page})`;
  }
  return `Source: page ${page}, ${status}`;
}
