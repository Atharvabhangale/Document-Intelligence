import { BookOpenText, Eye } from "lucide-react";

import type { Citation, CitationStatus } from "../../api/types";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { cx } from "../../lib/cx";
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

const LEGEND: readonly { status: CitationStatus; text: string }[] = [
  { status: "verified", text: "found on the cited page" },
  { status: "relocated", text: "found on another page" },
  { status: "approximate", text: "close match only" },
  { status: "unverified", text: "not found" },
  { status: "invalid_page", text: "page does not exist" },
];

const LEGEND_ICON_TONE: Readonly<Record<Tone, string>> = {
  success: "text-success",
  info: "text-info",
  warning: "text-warning",
  danger: "text-danger",
  neutral: "text-muted",
  ai: "text-ai",
};

/** One-line explanation of the verification statuses (wraps on narrow screens). */
function StatusLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-surface-muted px-4 py-2 text-xs text-muted">
      <span>Quotes checked automatically against the document text:</span>
      {LEGEND.map(({ status, text }) => (
        <span key={status} className="inline-flex items-center gap-1 whitespace-nowrap">
          <CitationStatusIcon
            status={status}
            className={cx("size-3", LEGEND_ICON_TONE[CITATION_STATUS[status].tone])}
          />
          <span>
            <strong className="font-medium text-ink">{CITATION_STATUS[status].label}</strong>:{" "}
            {text}
          </span>
        </span>
      ))}
    </div>
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
          <StatusLegend />
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
