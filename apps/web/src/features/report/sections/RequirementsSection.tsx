import { ClipboardList, Funnel } from "lucide-react";
import { useState } from "react";

import type { Citation, Requirement } from "../../../api/types";
import { EmptyState } from "../../../components/ui/EmptyState";
import { useIsWide } from "../../../hooks/useMediaQuery";
import { cx } from "../../../lib/cx";
import { BasisTag, ObligationBadge } from "../badges";
import { CitationChips } from "../CitationChip";
import { resolveCitations, type CitationIndex } from "../citations";
import { SectionCard } from "../SectionCard";
import type { SectionControls } from "./types";

export type RequirementFilter = "all" | "mandatory" | "inferred";

const FILTERS: { value: RequirementFilter; label: string; test: (r: Requirement) => boolean }[] = [
  { value: "all", label: "All", test: () => true },
  { value: "mandatory", label: "Mandatory", test: (r) => r.obligation === "mandatory" },
  { value: "inferred", label: "Inferred", test: (r) => r.basis === "inferred" },
];

interface RequirementsSectionProps extends SectionControls {
  requirements: readonly Requirement[];
  index: CitationIndex;
  onOpenCitation: (citation: Citation) => void;
}

export function RequirementsSection({
  requirements,
  index,
  onOpenCitation,
  ...controls
}: RequirementsSectionProps) {
  const [filter, setFilter] = useState<RequirementFilter>("all");
  const wide = useIsWide();
  const active = FILTERS.find((f) => f.value === filter) ?? FILTERS[0]!;
  const visible = requirements.filter(active.test);

  const toolbar =
    requirements.length > 0 ? (
      <div
        role="group"
        aria-label="Filter requirements"
        className="inline-flex items-center rounded-control border border-line bg-surface-muted p-0.5"
      >
        <Funnel aria-hidden="true" className="mx-1 size-3.5 text-subtle max-sm:hidden" />
        {FILTERS.map((option) => {
          const count = requirements.filter(option.test).length;
          const selected = option.value === filter;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => setFilter(option.value)}
              className={cx(
                "tabular-nums h-6 rounded px-2 text-xs font-medium whitespace-nowrap transition-colors",
                selected ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink",
              )}
            >
              {option.label} <span className="text-muted">{count}</span>
            </button>
          );
        })}
      </div>
    ) : null;

  return (
    <SectionCard
      id="section-requirements"
      title="Requirements"
      count={requirements.length}
      toolbar={toolbar}
      {...controls}
    >
      {requirements.length === 0 ? (
        <EmptyState
          compact
          icon={<ClipboardList />}
          title="No explicit requirements were identified in this document."
        />
      ) : visible.length === 0 ? (
        <EmptyState compact icon={<Funnel />} title="No requirements match this filter." />
      ) : wide ? (
        <RequirementsTable requirements={visible} index={index} onOpenCitation={onOpenCitation} />
      ) : (
        <RequirementsList requirements={visible} index={index} onOpenCitation={onOpenCitation} />
      )}
    </SectionCard>
  );
}

interface ListProps {
  requirements: readonly Requirement[];
  index: CitationIndex;
  onOpenCitation: (citation: Citation) => void;
}

const TH = "px-3 py-2 text-left text-xs font-semibold text-muted first:pl-4 last:pr-4";
const TD = "px-3 py-2.5 align-top first:pl-4 last:pr-4";

function RequirementsTable({ requirements, index, onOpenCitation }: ListProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-surface-muted">
          <tr className="border-b border-line">
            <th scope="col" className={cx(TH, "w-24")}>
              ID
            </th>
            <th scope="col" className={TH}>
              Requirement
            </th>
            <th scope="col" className={cx(TH, "w-28")}>
              Obligation
            </th>
            <th scope="col" className={cx(TH, "w-24")}>
              Basis
            </th>
            <th scope="col" className={cx(TH, "w-28")}>
              Category
            </th>
            <th scope="col" className={cx(TH, "w-32")}>
              Sources
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {requirements.map((requirement) => (
            <tr key={requirement.id} className="hover:bg-surface-muted/60">
              <td className={cx(TD, "font-mono text-xs whitespace-nowrap text-muted tabular-nums")}>
                {requirement.id}
              </td>
              <td className={cx(TD, "text-ink")}>{requirement.statement}</td>
              <td className={TD}>
                <ObligationBadge obligation={requirement.obligation} />
              </td>
              <td className={TD}>
                <BasisTag basis={requirement.basis} />
              </td>
              <td className={cx(TD, "text-muted")}>{requirement.category ?? "—"}</td>
              <td className={TD}>
                <CitationChips
                  citations={resolveCitations(requirement.citationIds, index)}
                  onOpen={onOpenCitation}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Narrow screens: one stacked card per requirement. */
function RequirementsList({ requirements, index, onOpenCitation }: ListProps) {
  return (
    <ul className="divide-y divide-line">
      {requirements.map((requirement) => (
        <li key={requirement.id} className="space-y-2 px-4 py-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 font-mono text-xs text-muted tabular-nums">{requirement.id}</span>
            <ObligationBadge obligation={requirement.obligation} />
            <BasisTag basis={requirement.basis} />
            {requirement.category ? (
              <span className="text-xs text-muted">· {requirement.category}</span>
            ) : null}
          </div>
          <p className="text-ink">{requirement.statement}</p>
          <CitationChips
            citations={resolveCitations(requirement.citationIds, index)}
            onOpen={onOpenCitation}
          />
        </li>
      ))}
    </ul>
  );
}
