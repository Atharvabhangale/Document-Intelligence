/**
 * Plain-text summary (for "Copy summary") and JSON export of a report.
 *
 * Output is plain text / JSON only — never HTML.
 */
import type { DocumentIntelligenceReport } from "../../api/types";
import { formatDateTime, formatVersion } from "../../lib/format";
import { citationPages, indexCitations, resolveCitations, type CitationIndex } from "./citations";

function pageRef(ids: readonly string[], index: CitationIndex): string {
  const pages = citationPages(resolveCitations(ids, index));
  if (pages.length === 0) return "";
  return pages.length === 1 ? ` (p. ${pages[0]})` : ` (pp. ${pages.join(", ")})`;
}

/**
 * Plain-text summary: document identity, executive summary and key points with page references.
 */
export function buildSummaryText(report: DocumentIntelligenceReport): string {
  const { metadata } = report.document;
  const index = indexCitations(report.citations);
  const identity = [
    metadata.number ? `Number: ${metadata.number}` : null,
    `Revision: ${formatVersion(metadata) ?? "—"}`,
    `State: ${metadata.state ?? "—"}`,
  ].filter((part): part is string => part !== null);

  const lines: string[] = [
    metadata.name,
    identity.join(" | "),
    "",
    "Executive summary",
    `${report.summary.executive.text}${pageRef(report.summary.executive.citationIds, index)}`,
  ];

  if (report.summary.keyPoints.length > 0) {
    lines.push("", "Key points");
    report.summary.keyPoints.forEach((point, position) => {
      lines.push(`${position + 1}. ${point.text}${pageRef(point.citationIds, index)}`);
    });
  }

  const { model, generatedAt } = report.provenance;
  lines.push(
    "",
    `AI-generated (${model}, ${formatDateTime(generatedAt)}). ` +
      "Verify against the source document before use.",
  );
  return lines.join("\n");
}

function safeFilePart(value: string): string {
  return value.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
}

/** `<number>_<rev.iter>_ai-report.json`, e.g. "SOP-00123_A.3_ai-report.json". */
export function reportFileName(report: DocumentIntelligenceReport): string {
  const { metadata, documentId } = report.document;
  const parts = [
    safeFilePart(metadata.number ?? "") || safeFilePart(documentId) || "document",
    safeFilePart(formatVersion(metadata) ?? ""),
  ].filter(Boolean);
  return `${parts.join("_")}_ai-report.json`;
}

/** Trigger a browser download of the report as formatted JSON. */
export function downloadReportJson(report: DocumentIntelligenceReport): void {
  const blob = new Blob([`${JSON.stringify(report, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = reportFileName(report);
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke after the click has been processed.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
