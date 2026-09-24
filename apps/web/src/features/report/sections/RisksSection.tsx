import { ShieldCheck } from "lucide-react";

import type { Citation, Risk } from "../../../api/types";
import { EmptyState } from "../../../components/ui/EmptyState";
import { BasisTag, SEVERITY_ORDER, SeverityBadge } from "../badges";
import { CitationChips } from "../CitationChip";
import { resolveCitations, type CitationIndex } from "../citations";
import { SectionCard } from "../SectionCard";
import type { SectionControls } from "./types";

interface RisksSectionProps extends SectionControls {
  risks: readonly Risk[];
  index: CitationIndex;
  onOpenCitation: (citation: Citation) => void;
}

/** Risks ordered high → medium → low (stable within a severity). */
export function sortRisks(risks: readonly Risk[]): Risk[] {
  return [...risks].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

export function RisksSection({ risks, index, onOpenCitation, ...controls }: RisksSectionProps) {
  const sorted = sortRisks(risks);
  return (
    <SectionCard id="section-risks" title="Risks & Concerns" count={risks.length} {...controls}>
      {sorted.length === 0 ? (
        <EmptyState
          compact
          icon={<ShieldCheck />}
          title="No risks or concerns were identified in this document."
        />
      ) : (
        <ul className="divide-y divide-line">
          {sorted.map((risk) => (
            <li key={risk.id} className="space-y-1.5 px-4 py-3" data-testid="risk-item">
              <div className="flex flex-wrap items-start gap-2">
                <SeverityBadge severity={risk.severity} />
                <h3 className="min-w-0 flex-1 text-sm font-semibold text-ink">{risk.title}</h3>
                <BasisTag basis={risk.basis} />
              </div>
              <p className="text-ink/90">{risk.description}</p>
              <CitationChips
                citations={resolveCitations(risk.citationIds, index)}
                onOpen={onOpenCitation}
              />
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
