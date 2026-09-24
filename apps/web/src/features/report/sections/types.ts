/** Collapse state passed from ReportView to every section card. */
export interface SectionControls {
  collapsed: boolean;
  onToggle: () => void;
}
