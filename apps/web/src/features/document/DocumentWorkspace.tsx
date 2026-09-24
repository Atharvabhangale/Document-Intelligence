import { ArrowLeft, ScanText } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getCachedReport,
  getDocument,
  isAbortError,
  summarize,
  toApiError,
  type ApiError,
} from "../../api/client";
import type {
  Citation,
  DocumentIntelligenceReport,
  DocumentRecord,
  HealthResponse,
} from "../../api/types";
import { ErrorState } from "../../components/ErrorState";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Notice } from "../../components/ui/Notice";
import { formatVersion } from "../../lib/format";
import { AskPanel } from "../ask/AskPanel";
import { AnalysisProgress, ReportSkeleton } from "../report/AnalysisProgress";
import { AnalysisRail } from "../report/AnalysisRail";
import { ReportView } from "../report/ReportView";
import { SourceViewer } from "../report/SourceViewer";
import { Breadcrumb } from "./Breadcrumb";
import { DocumentHeader, DocumentHeaderSkeleton } from "./DocumentHeader";
import { HeaderActions } from "./HeaderActions";
import { useDocumentPages } from "./useDocumentPages";

type Loadable<T> =
  { status: "loading" } | { status: "ready"; value: T } | { status: "error"; error: ApiError };

type AnalysisState =
  | { status: "idle" }
  | { status: "running"; startedAt: number; refresh: boolean }
  | { status: "error"; error: ApiError; refresh: boolean };

interface DocumentWorkspaceProps {
  documentId: string;
  /** Start the analysis automatically when no cached report exists (Windchill launch). */
  autorun: boolean;
  health: HealthResponse | null;
  onHome: () => void;
  /** Reports whether the open document comes from a development-only source. */
  onDevelopmentOnlyChange: (developmentOnly: boolean) => void;
}

const APP_TITLE = "Document Intelligence";

export function DocumentWorkspace({
  documentId,
  autorun,
  health,
  onHome,
  onDevelopmentOnlyChange,
}: DocumentWorkspaceProps) {
  const [record, setRecord] = useState<Loadable<DocumentRecord>>({ status: "loading" });
  const [cached, setCached] = useState<Loadable<DocumentIntelligenceReport | null>>({
    status: "loading",
  });
  const [analysis, setAnalysis] = useState<AnalysisState>({ status: "idle" });
  const [reloadKey, setReloadKey] = useState(0);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const { state: pagesState, load: loadPages } = useDocumentPages(documentId);

  const mounted = useRef(false);
  const analysisSeq = useRef(0);
  const autorunStarted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Document metadata and the cached report, loaded in parallel.
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    setRecord({ status: "loading" });
    setCached({ status: "loading" });
    getDocument(documentId, { signal })
      .then((value) => setRecord({ status: "ready", value }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) setRecord({ status: "error", error: toApiError(error) });
      });
    getCachedReport(documentId, "summarize", { signal })
      .then((value) => setCached({ status: "ready", value }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) setCached({ status: "error", error: toApiError(error) });
      });
    return () => controller.abort();
  }, [documentId, reloadKey]);

  const loadedRecord = record.status === "ready" ? record.value : null;

  useEffect(() => {
    if (!loadedRecord) return;
    onDevelopmentOnlyChange(loadedRecord.developmentOnly);
    const { number, name } = loadedRecord.metadata;
    document.title = `${number ? `${number} ${name}` : name} · ${APP_TITLE}`;
  }, [loadedRecord, onDevelopmentOnlyChange]);

  useEffect(
    () => () => {
      document.title = APP_TITLE;
    },
    [],
  );

  const startAnalysis = useCallback(
    (refresh: boolean) => {
      const seq = ++analysisSeq.current;
      setAnalysis({ status: "running", startedAt: Date.now(), refresh });
      // Not aborted on unmount on purpose: the backend caches the finished report, so leaving
      // the page does not waste the run. Results for a stale run are ignored.
      summarize(documentId, { refresh })
        .then((report) => {
          if (!mounted.current || seq !== analysisSeq.current) return;
          setCached({ status: "ready", value: report });
          setAnalysis({ status: "idle" });
        })
        .catch((error: unknown) => {
          if (!mounted.current || seq !== analysisSeq.current) return;
          setAnalysis({ status: "error", error: toApiError(error), refresh });
        });
    },
    [documentId],
  );

  // Windchill launch with autorun=1: analyze once when there is no cached report.
  useEffect(() => {
    if (!autorun || autorunStarted.current) return;
    if (record.status !== "ready" || cached.status !== "ready" || cached.value !== null) return;
    if (health && !health.ai.configured) return;
    autorunStarted.current = true;
    startAnalysis(false);
  }, [autorun, record.status, cached, health, startAnalysis]);

  const openCitation = useCallback(
    (citation: Citation) => {
      loadPages();
      setActiveCitation(citation);
    },
    [loadPages],
  );
  const closeCitation = useCallback(() => setActiveCitation(null), []);

  if (record.status === "loading") {
    return (
      <div className="space-y-4" aria-busy="true">
        <p role="status" className="sr-only">
          Loading document
        </p>
        <DocumentHeaderSkeleton />
        <ReportSkeleton />
      </div>
    );
  }

  if (record.status === "error") {
    return (
      <div className="mx-auto max-w-2xl py-6">
        <ErrorState
          error={record.error}
          onRetry={() => setReloadKey((key) => key + 1)}
          actions={
            <Button size="sm" icon={<ArrowLeft />} onClick={onHome}>
              All documents
            </Button>
          }
        />
      </div>
    );
  }

  const doc = record.value;
  const report = cached.status === "ready" ? cached.value : null;
  const analyzing = analysis.status === "running";
  const aiAvailable = health ? health.ai.configured : true;
  const breadcrumbCurrent = [doc.metadata.number, formatVersion(doc.metadata)]
    .filter(Boolean)
    .join(" ");

  let content;
  if (cached.status === "loading") {
    content = (
      <div aria-busy="true">
        <p role="status" className="sr-only">
          Loading analysis
        </p>
        <ReportSkeleton />
      </div>
    );
  } else if (cached.status === "error") {
    content = <ErrorState error={cached.error} onRetry={() => setReloadKey((key) => key + 1)} />;
  } else if (analysis.status === "running") {
    content = (
      <AnalysisProgress
        startedAt={analysis.startedAt}
        pageCount={doc.extraction.pageCount}
        model={health?.ai.model ?? null}
      />
    );
  } else {
    const failure =
      analysis.status === "error" ? (
        <ErrorState
          error={analysis.error}
          onRetry={() => startAnalysis(analysis.refresh)}
          actions={
            report ? (
              <span className="self-center text-xs text-muted">
                Showing the previous analysis below.
              </span>
            ) : null
          }
        />
      ) : null;
    content = report ? (
      <>
        {failure}
        <ReportView report={report} onOpenCitation={openCitation} showAskInNav />
      </>
    ) : (
      (failure ?? <NotAnalyzed aiAvailable={aiAvailable} onAnalyze={() => startAnalysis(false)} />)
    );
  }

  return (
    <div className="space-y-4">
      <Breadcrumb
        location={doc.metadata.location}
        current={breadcrumbCurrent || doc.metadata.name}
        onHome={onHome}
      />
      <DocumentHeader
        record={doc}
        actions={
          <HeaderActions
            report={report}
            loading={cached.status !== "ready"}
            analyzing={analyzing}
            aiAvailable={aiAvailable}
            onAnalyze={() => startAnalysis(false)}
            onReanalyze={() => startAnalysis(true)}
          />
        }
      />
      <div className="grid grid-cols-1 items-start gap-4 wide:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          {content}
          <AskPanel
            documentId={documentId}
            documentType={doc.metadata.documentType}
            maxQuestionChars={health?.limits.maxQuestionChars}
            aiAvailable={aiAvailable}
            onOpenCitation={openCitation}
          />
        </div>
        <aside
          aria-label="Analysis details"
          className="min-w-0 wide:sticky wide:top-2 wide:max-h-[calc(100vh-1rem)] wide:overflow-y-auto"
        >
          {/* While re-analyzing, the previous provenance would describe a report not shown. */}
          <AnalysisRail record={doc} report={analyzing ? null : report} />
        </aside>
      </div>
      {activeCitation ? (
        <SourceViewer
          documentId={documentId}
          citation={activeCitation}
          pageCount={doc.extraction.pageCount}
          pages={pagesState}
          onRetryPages={loadPages}
          onClose={closeCitation}
        />
      ) : null}
    </div>
  );
}

function NotAnalyzed({ aiAvailable, onAnalyze }: { aiAvailable: boolean; onAnalyze: () => void }) {
  return (
    <Card className="px-6 py-10">
      <div className="mx-auto flex max-w-lg flex-col items-center gap-3 text-center">
        <span
          aria-hidden="true"
          className="flex size-11 items-center justify-center rounded-full bg-primary-bg text-primary"
        >
          <ScanText className="size-5" />
        </span>
        <h2 className="text-base font-semibold text-ink">
          This document has not been analyzed yet
        </h2>
        <p className="text-muted">
          Analyze it to generate a structured summary, requirements, specifications, risks and
          recommended actions. Every statement cites the page it is based on, and each quote is
          checked against the document text.
        </p>
        <Button variant="primary" onClick={onAnalyze} disabled={!aiAvailable}>
          Analyze document
        </Button>
        <p className="text-xs text-muted">Usually takes 10–40 seconds.</p>
        {aiAvailable ? null : (
          <Notice tone="warning" className="text-left">
            Analysis is unavailable: the AI provider is not configured on the server. Contact your
            administrator.
          </Notice>
        )}
      </div>
    </Card>
  );
}
