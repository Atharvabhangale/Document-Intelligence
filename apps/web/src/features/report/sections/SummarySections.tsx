import { ListOrdered } from "lucide-react";

import type { Citation, SummarySection } from "../../../api/types";
import { EmptyState } from "../../../components/ui/EmptyState";
import { AiGeneratedTag } from "../badges";
import { CitationChips } from "../CitationChip";
import { resolveCitations, type CitationIndex } from "../citations";
import { SectionCard } from "../SectionCard";
import type { SectionControls } from "./types";

interface SummaryProps extends SectionControls {
  summary: SummarySection;
  index: CitationIndex;
  onOpenCitation: (citation: Citation) => void;
}

export function ExecutiveSummaryCard({
  summary,
  index,
  onOpenCitation,
  ...controls
}: SummaryProps) {
  return (
    <SectionCard
      id="section-summary"
      title="Executive Summary"
      badge={<AiGeneratedTag />}
      {...controls}
    >
      <div className="space-y-4 px-4 py-4">
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted uppercase">Purpose</p>
          <p className="mt-1 text-muted">{summary.purpose}</p>
        </div>
        <div className="space-y-2">
          <p className="text-[15px] leading-relaxed text-ink">{summary.executive.text}</p>
          <CitationChips
            citations={resolveCitations(summary.executive.citationIds, index)}
            onOpen={onOpenCitation}
          />
        </div>
      </div>
    </SectionCard>
  );
}

export function KeyPointsCard({ summary, index, onOpenCitation, ...controls }: SummaryProps) {
  const points = summary.keyPoints;
  return (
    <SectionCard id="section-key-points" title="Key Points" count={points.length} {...controls}>
      {points.length === 0 ? (
        <EmptyState compact icon={<ListOrdered />} title="No key points were identified." />
      ) : (
        <ol className="divide-y divide-line">
          {points.map((point, position) => (
            <li key={point.id} className="flex gap-3 px-4 py-3">
              <span
                aria-hidden="true"
                className="tabular-nums mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-neutral-bg text-xs font-semibold text-muted"
              >
                {position + 1}
              </span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-ink">{point.text}</p>
                <CitationChips
                  citations={resolveCitations(point.citationIds, index)}
                  onOpen={onOpenCitation}
                />
              </div>
            </li>
          ))}
        </ol>
      )}
    </SectionCard>
  );
}
