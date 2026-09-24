import { Info, ListChecks } from "lucide-react";

import type { Citation, RecommendedAction } from "../../../api/types";
import { EmptyState } from "../../../components/ui/EmptyState";
import { BasisTag, PRIORITY_ORDER, PriorityBadge } from "../badges";
import { CitationChips } from "../CitationChip";
import { resolveCitations, type CitationIndex } from "../citations";
import { SectionCard } from "../SectionCard";
import type { SectionControls } from "./types";

interface ActionsSectionProps extends SectionControls {
  actions: readonly RecommendedAction[];
  index: CitationIndex;
  onOpenCitation: (citation: Citation) => void;
}

export function ActionsSection({
  actions,
  index,
  onOpenCitation,
  ...controls
}: ActionsSectionProps) {
  const sorted = [...actions].sort(
    (a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority],
  );
  return (
    <SectionCard
      id="section-actions"
      title="Recommended Actions"
      count={actions.length}
      footer={
        sorted.length > 0 ? (
          <p className="flex items-center gap-1.5 border-t border-line px-4 py-2 text-xs text-muted">
            <Info aria-hidden="true" className="size-3.5 shrink-0" />
            Recommendations are AI-generated. Review before acting.
          </p>
        ) : null
      }
      {...controls}
    >
      {sorted.length === 0 ? (
        <EmptyState
          compact
          icon={<ListChecks />}
          title="No actions were recommended for this document."
        />
      ) : (
        <ul className="divide-y divide-line">
          {sorted.map((action) => (
            <li key={action.id} className="space-y-1.5 px-4 py-3">
              <div className="flex flex-wrap items-start gap-2">
                <PriorityBadge priority={action.priority} />
                <h3 className="min-w-0 flex-1 text-sm font-semibold text-ink">{action.action}</h3>
                <BasisTag basis={action.basis} />
              </div>
              <p className="text-muted">{action.rationale}</p>
              <CitationChips
                citations={resolveCitations(action.citationIds, index)}
                onOpen={onOpenCitation}
              />
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
