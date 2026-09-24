import { Ruler } from "lucide-react";

import type { Citation, Specification } from "../../../api/types";
import { EmptyState } from "../../../components/ui/EmptyState";
import { useIsWide } from "../../../hooks/useMediaQuery";
import { cx } from "../../../lib/cx";
import { CitationChips } from "../CitationChip";
import { resolveCitations, type CitationIndex } from "../citations";
import { SectionCard } from "../SectionCard";
import type { SectionControls } from "./types";

interface SpecificationsSectionProps extends SectionControls {
  specifications: readonly Specification[];
  index: CitationIndex;
  onOpenCitation: (citation: Citation) => void;
}

function SpecValue({ spec }: { spec: Specification }) {
  return (
    <span className="font-mono text-[13px] text-ink tabular-nums">
      {spec.value}
      {spec.unit ? <span className="text-muted"> {spec.unit}</span> : null}
    </span>
  );
}

const TH = "px-3 py-2 text-left text-xs font-semibold text-muted first:pl-4 last:pr-4";
const TD = "px-3 py-2.5 align-top first:pl-4 last:pr-4";

export function SpecificationsSection({
  specifications,
  index,
  onOpenCitation,
  ...controls
}: SpecificationsSectionProps) {
  const wide = useIsWide();
  return (
    <SectionCard
      id="section-specifications"
      title="Specifications"
      count={specifications.length}
      {...controls}
    >
      {specifications.length === 0 ? (
        <EmptyState
          compact
          icon={<Ruler />}
          title="No specifications or parameter values were identified in this document."
        />
      ) : wide ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-surface-muted">
              <tr className="border-b border-line">
                <th scope="col" className={cx(TH, "w-[28%]")}>
                  Parameter
                </th>
                <th scope="col" className={cx(TH, "w-[22%]")}>
                  Value
                </th>
                <th scope="col" className={TH}>
                  Context
                </th>
                <th scope="col" className={cx(TH, "w-32")}>
                  Sources
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {specifications.map((spec) => (
                <tr key={spec.id} className="hover:bg-surface-muted/60">
                  <th scope="row" className={cx(TD, "text-left font-medium text-ink")}>
                    {spec.parameter}
                  </th>
                  <td className={TD}>
                    <SpecValue spec={spec} />
                  </td>
                  <td className={cx(TD, "text-muted")}>{spec.context ?? "—"}</td>
                  <td className={TD}>
                    <CitationChips
                      citations={resolveCitations(spec.citationIds, index)}
                      onOpen={onOpenCitation}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {specifications.map((spec) => (
            <li key={spec.id} className="space-y-1.5 px-4 py-3">
              <p className="font-medium text-ink">{spec.parameter}</p>
              <SpecValue spec={spec} />
              {spec.context ? <p className="text-muted">{spec.context}</p> : null}
              <CitationChips
                citations={resolveCitations(spec.citationIds, index)}
                onOpen={onOpenCitation}
              />
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
