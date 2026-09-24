import { useMemo, useState } from "react";

import type { Citation, DocumentIntelligenceReport } from "../../api/types";
import { useActiveSection } from "../../hooks/useActiveSection";
import { indexCitations } from "./citations";
import { SectionNav, type NavItem } from "./SectionNav";
import { ActionsSection } from "./sections/ActionsSection";
import { RequirementsSection } from "./sections/RequirementsSection";
import { RisksSection } from "./sections/RisksSection";
import { SpecificationsSection } from "./sections/SpecificationsSection";
import { ExecutiveSummaryCard, KeyPointsCard } from "./sections/SummarySections";
import { SourcesSection } from "./SourcesSection";

/** Id of the Ask panel rendered after the report (target of the "Ask" navigation item). */
export const ASK_SECTION_ID = "section-ask";

type SectionKey =
  "summary" | "keyPoints" | "requirements" | "specifications" | "risks" | "actions" | "sources";

interface ReportViewProps {
  report: DocumentIntelligenceReport;
  onOpenCitation: (citation: Citation) => void;
  /** Adds an "Ask" item to the navigation (the Ask panel itself is rendered by the caller). */
  showAskInNav?: boolean;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * The structured report: sticky section navigation followed by the section cards.
 *
 * Rendered as a fragment so the sticky navigation spans the whole main column, including the
 * Ask panel the caller renders after it.
 */
export function ReportView({ report, onOpenCitation, showAskInNav = false }: ReportViewProps) {
  const index = useMemo(() => indexCitations(report.citations), [report.citations]);
  const [collapsed, setCollapsed] = useState<Partial<Record<SectionKey, boolean>>>({});

  const navItems: NavItem[] = [
    { id: "section-summary", label: "Summary", alsoActiveFor: ["section-key-points"] },
    { id: "section-requirements", label: "Requirements", count: report.requirements.length },
    { id: "section-specifications", label: "Specifications", count: report.specifications.length },
    { id: "section-risks", label: "Risks", count: report.risks.length },
    { id: "section-actions", label: "Actions", count: report.actions.length },
    { id: "section-sources", label: "Sources", count: report.citations.length },
    ...(showAskInNav ? [{ id: ASK_SECTION_ID, label: "Ask" }] : []),
  ];
  const observed = [
    "section-summary",
    "section-key-points",
    ...navItems.slice(1).map((item) => item.id),
  ];
  const activeId = useActiveSection(observed);

  const controls = (key: SectionKey) => ({
    collapsed: collapsed[key] === true,
    onToggle: () => setCollapsed((state) => ({ ...state, [key]: !state[key] })),
  });

  const navigate = (id: string) => {
    const key = SECTION_KEYS[id];
    if (key) setCollapsed((state) => ({ ...state, [key]: false }));
    // Wait for an expanded section to render before scrolling to it.
    requestAnimationFrame(() => {
      const target = document.getElementById(id);
      if (!target) return;
      target.scrollIntoView?.({
        behavior: prefersReducedMotion() ? "auto" : "smooth",
        block: "start",
      });
      const heading = target.querySelector<HTMLElement>("h2");
      heading?.focus({ preventScroll: true });
    });
  };

  return (
    <>
      <SectionNav items={navItems} activeId={activeId} onNavigate={navigate} />
      <ExecutiveSummaryCard
        summary={report.summary}
        index={index}
        onOpenCitation={onOpenCitation}
        {...controls("summary")}
      />
      <KeyPointsCard
        summary={report.summary}
        index={index}
        onOpenCitation={onOpenCitation}
        {...controls("keyPoints")}
      />
      <RequirementsSection
        requirements={report.requirements}
        index={index}
        onOpenCitation={onOpenCitation}
        {...controls("requirements")}
      />
      <SpecificationsSection
        specifications={report.specifications}
        index={index}
        onOpenCitation={onOpenCitation}
        {...controls("specifications")}
      />
      <RisksSection
        risks={report.risks}
        index={index}
        onOpenCitation={onOpenCitation}
        {...controls("risks")}
      />
      <ActionsSection
        actions={report.actions}
        index={index}
        onOpenCitation={onOpenCitation}
        {...controls("actions")}
      />
      <SourcesSection
        citations={report.citations}
        onOpenCitation={onOpenCitation}
        {...controls("sources")}
      />
    </>
  );
}

const SECTION_KEYS: Readonly<Record<string, SectionKey>> = {
  "section-summary": "summary",
  "section-key-points": "keyPoints",
  "section-requirements": "requirements",
  "section-specifications": "specifications",
  "section-risks": "risks",
  "section-actions": "actions",
  "section-sources": "sources",
};
