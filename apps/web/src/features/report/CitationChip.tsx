import type { Citation } from "../../api/types";
import { cx } from "../../lib/cx";
import { CitationStatusIcon } from "./CitationStatusIcon";
import { CITATION_STATUS, citationLabel, citationTooltip, displayPage } from "./citations";

const CHIP_TONES = {
  success: "border-success/30 bg-success-bg text-success hover:border-success/60",
  info: "border-info/30 bg-info-bg text-info hover:border-info/60",
  warning: "border-warning/30 bg-warning-bg text-warning hover:border-warning/60",
  danger: "border-danger/30 bg-danger-bg text-danger hover:border-danger/60",
  neutral: "border-line-strong bg-neutral-bg text-muted hover:border-subtle",
  ai: "border-ai/30 bg-ai-bg text-ai hover:border-ai/60",
} as const;

interface CitationChipProps {
  citation: Citation;
  onOpen: (citation: Citation) => void;
}

/** Small "p. 4" pill with a status icon; opens the source viewer. */
export function CitationChip({ citation, onOpen }: CitationChipProps) {
  const meta = CITATION_STATUS[citation.status];
  const page = displayPage(citation);
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      aria-label={citationLabel(citation)}
      title={citationTooltip(citation)}
      className={cx(
        "tabular-nums inline-flex h-5 items-center gap-1 rounded-full border px-1.5 text-xs font-medium transition-colors",
        CHIP_TONES[meta.tone],
      )}
    >
      <CitationStatusIcon status={citation.status} className="size-3" />
      <span>p. {page}</span>
    </button>
  );
}

/** Muted tag for items that carry no citations. */
export function NoSourceTag() {
  return (
    <span
      title="The AI did not cite a source for this item."
      className="inline-flex h-5 items-center rounded-full border border-dashed border-line-strong px-1.5 text-xs text-muted"
    >
      No source
    </span>
  );
}

interface CitationChipsProps {
  citations: readonly Citation[];
  onOpen: (citation: Citation) => void;
  className?: string;
}

/** Chips for an item's citations, or a "No source" tag. */
export function CitationChips({ citations, onOpen, className }: CitationChipsProps) {
  if (citations.length === 0) {
    return (
      <span className={cx("inline-flex", className)}>
        <NoSourceTag />
      </span>
    );
  }
  return (
    <span className={cx("inline-flex flex-wrap items-center gap-1", className)}>
      {citations.map((citation) => (
        <CitationChip key={citation.id} citation={citation} onOpen={onOpen} />
      ))}
    </span>
  );
}
