import { Check, Copy, Download, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { DocumentIntelligenceReport } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { copyText } from "../../lib/clipboard";
import { buildSummaryText, downloadReportJson } from "../report/reportExport";

interface HeaderActionsProps {
  report: DocumentIntelligenceReport | null;
  /** The cached report is still loading: actions are not offered yet. */
  loading: boolean;
  analyzing: boolean;
  aiAvailable: boolean;
  onAnalyze: () => void;
  onReanalyze: () => void;
}

type CopyState = "idle" | "copied" | "failed";

export function HeaderActions({
  report,
  loading,
  analyzing,
  aiAvailable,
  onAnalyze,
  onReanalyze,
}: HeaderActionsProps) {
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const resetTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  if (loading) return null;
  const unavailableTitle = aiAvailable
    ? undefined
    : "The AI provider is not configured on the server.";

  if (!report) {
    return (
      <Button
        variant="primary"
        icon={<Sparkles />}
        onClick={onAnalyze}
        loading={analyzing}
        disabled={!aiAvailable}
        title={unavailableTitle}
      >
        {analyzing ? "Analyzing…" : "Analyze document"}
      </Button>
    );
  }

  const copy = async () => {
    const ok = await copyText(buildSummaryText(report));
    setCopyState(ok ? "copied" : "failed");
    window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setCopyState("idle"), 2000);
  };

  return (
    <>
      <Button
        icon={<RefreshCw />}
        onClick={onReanalyze}
        loading={analyzing}
        disabled={!aiAvailable}
        title={unavailableTitle ?? "Run the analysis again, ignoring the cached report"}
      >
        {analyzing ? "Analyzing…" : "Re-analyze"}
      </Button>
      <Button
        icon={
          copyState === "copied" ? <Check /> : copyState === "failed" ? <TriangleAlert /> : <Copy />
        }
        onClick={() => void copy()}
        disabled={analyzing}
        title="Copy the executive summary and key points as plain text"
      >
        {copyState === "copied"
          ? "Copied"
          : copyState === "failed"
            ? "Copy failed"
            : "Copy summary"}
      </Button>
      <Button
        icon={<Download />}
        onClick={() => downloadReportJson(report)}
        disabled={analyzing}
        title="Download the full report as JSON"
      >
        Export JSON
      </Button>
      <span aria-live="polite" className="sr-only">
        {copyState === "copied"
          ? "Summary copied to the clipboard"
          : copyState === "failed"
            ? "Copy failed"
            : ""}
      </span>
    </>
  );
}
