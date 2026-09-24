import { BookOpenText, Eye } from "lucide-react";

import type { Citation } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { CitationStatusIcon } from "./CitationStatusIcon";
import { CITATION_STATUS, displayPage } from "./citations";
import { SectionCard } from "./SectionCard";
import type { SectionControls } from "./sections/types";

interface SourcesSectionProps extends SectionControls {
  citations: readonly Citation[];
  onOpenCitation: (citation: Citation) => void;
}

export function CitationStatusBadge({ citation }: { citation: Citation }) {
  const meta = CITATION_STATUS[citation.status];
  const page = displayPage(citation);
  const label =
    citation.status === "relocated" || (citation.status === "approximate" && page !== citation.page)
      ? `${meta.label} — found on p. ${page}`
      : meta.label;
  return (
    <Badge
      tone={meta.tone}
      icon={<CitationStatusIcon status={citation.status} />}
      title={meta.description}
    >
      {label}
    </Badge>
  );
}

export function SourcesSection({ citations, onOpenCitation, ...controls }: SourcesSectionProps) {
  return (
    <SectionCard id="section-sources" title="Sources" count={citations.length} {...controls}>
      {citations.length === 0 ? (
        <EmptyState
          compact
          icon={<BookOpenText />}
          title="The analysis did not cite any sources."
        />
      ) : (
        <>
          <p className="border-b border-line bg-surface-muted px-4 py-2 text-xs text-muted">
            Each quote cited by the AI was checked automatically against the extracted document
            text. <strong className="font-medium text-ink">Verified</strong>: found on the cited
            page · <strong className="font-medium text-ink">Relocated</strong>: found on another
            page · <strong className="font-medium text-ink">Approximate</strong>: close match only ·{" "}
            <strong className="font-medium text-ink">Unverified</strong>: not found ·{" "}
            <strong className="font-medium text-ink">Invalid page</strong>: the page does not exist.
          </p>
          <ul className="divide-y divide-line">
            {citations.map((citation) => (
              <li
                key={citation.id}
                className="grid grid-cols-[2.25rem_1fr_auto] sm:grid-cols-[3rem_1fr_auto] items-start gap-x-3 gap-y-1 px-4 py-2.5"
              >
                <span className="font-mono text-xs leading-5 text-muted tabular-nums">
                  {citation.id}
                </span>
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-ink tabular-nums">
                      p. {citation.page}
                    </span>
                    <CitationStatusBadge citation={citation} />
                  </div>
                  <blockquote className="text-sm break-words text-muted">
                    “{citation.quote}”
                  </blockquote>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Eye />}
                  onClick={() => onOpenCitation(citation)}
                  aria-label={`View source ${citation.id} on page ${displayPage(citation)}`}
                >
                  View
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
    </SectionCard>
  );
}
