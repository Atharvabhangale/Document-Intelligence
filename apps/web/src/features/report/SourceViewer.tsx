import { ChevronLeft, ChevronRight, ExternalLink, FileText, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { contentUrl } from "../../api/client";
import type { Citation, ExtractedPage } from "../../api/types";
import { ErrorState } from "../../components/ErrorState";
import { Button, ButtonLink, IconButton } from "../../components/ui/Button";
import { Notice } from "../../components/ui/Notice";
import { SkeletonLines } from "../../components/ui/Skeleton";
import { findQuoteRange, type TextRange } from "../../lib/quote";
import { pdfPageUrl } from "../../lib/url";
import type { PagesState } from "../document/useDocumentPages";
import { CITATION_STATUS, displayPage } from "./citations";
import { CitationStatusBadge } from "./SourcesSection";

interface SourceViewerProps {
  documentId: string;
  citation: Citation;
  pageCount: number;
  pages: PagesState;
  onRetryPages: () => void;
  onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

function clampPage(page: number, pageCount: number): number {
  return Math.min(Math.max(page, 1), Math.max(pageCount, 1));
}

/**
 * Right-side drawer (full screen on mobile) showing a citation next to the extracted text of
 * its page, with the quote highlighted. Modal: Esc closes, focus is trapped inside and returns
 * to the element that opened it.
 */
export function SourceViewer({
  documentId,
  citation,
  pageCount,
  pages,
  onRetryPages,
  onClose,
}: SourceViewerProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const targetPage = displayPage(citation);
  const [page, setPage] = useState(() => clampPage(targetPage, pageCount));

  // Focus management: move focus in, restore it to the opener on close; lock page scroll.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const trapFocus = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const meta = CITATION_STATUS[citation.status];
  const pageExists = citation.page >= 1 && citation.page <= pageCount;
  const targetExists = targetPage >= 1 && targetPage <= pageCount;

  return (
    <div className="fixed inset-0 z-50">
      <div aria-hidden="true" className="absolute inset-0 bg-ink/30" onClick={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={trapFocus}
        className="absolute inset-y-0 right-0 flex w-full flex-col bg-surface shadow-drawer sm:w-[480px] sm:border-l sm:border-line"
      >
        <header className="border-b border-line">
          <div className="flex items-center gap-2 px-4 pt-3 pb-2">
            <FileText aria-hidden="true" className="size-4 shrink-0 text-muted" />
            <h2 id={titleId} className="min-w-0 flex-1 truncate text-[15px] font-semibold text-ink">
              Source {citation.id}
            </h2>
            <IconButton ref={closeRef} label="Close source viewer" onClick={onClose}>
              <X />
            </IconButton>
          </div>
          <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
            <div className="flex items-center gap-1">
              <IconButton
                size="sm"
                label="Previous page"
                disabled={page <= 1}
                onClick={() => setPage((p) => clampPage(p - 1, pageCount))}
                className="border border-line-strong"
              >
                <ChevronLeft />
              </IconButton>
              <span
                aria-live="polite"
                className="min-w-20 text-center text-sm text-ink tabular-nums"
              >
                Page {page} of {pageCount}
              </span>
              <IconButton
                size="sm"
                label="Next page"
                disabled={page >= pageCount}
                onClick={() => setPage((p) => clampPage(p + 1, pageCount))}
                className="border border-line-strong"
              >
                <ChevronRight />
              </IconButton>
            </div>
            <ButtonLink
              size="sm"
              variant="ghost"
              icon={<ExternalLink />}
              href={pdfPageUrl(contentUrl(documentId), page)}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto text-primary hover:text-primary-hover"
            >
              Open PDF at page {page}
            </ButtonLink>
          </div>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <section aria-label="Citation" className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <CitationStatusBadge citation={citation} />
              <span className="text-xs text-muted tabular-nums">Cited as page {citation.page}</span>
            </div>
            <p className="text-xs text-muted">
              {meta.description}
              {citation.status === "relocated" ? ` It was found on page ${targetPage}.` : ""}
              {!pageExists ? ` The document has ${pageCount} pages.` : ""}
            </p>
            <blockquote className="rounded-control border-l-2 border-line-strong bg-surface-muted px-3 py-2 text-sm text-ink">
              “{citation.quote}”
            </blockquote>
          </section>

          <section aria-labelledby={`${titleId}-text`} className="space-y-2">
            <h3
              id={`${titleId}-text`}
              className="text-xs font-semibold tracking-wide text-muted uppercase"
            >
              Extracted text — page {page}
            </h3>
            <PageText
              pages={pages}
              pageNumber={page}
              citation={citation}
              targetPage={targetExists ? targetPage : null}
              onGoToTarget={() => setPage(clampPage(targetPage, pageCount))}
              onRetry={onRetryPages}
            />
          </section>
        </div>
      </div>
    </div>
  );
}

interface PageTextProps {
  pages: PagesState;
  pageNumber: number;
  citation: Citation;
  /** Page holding the evidence, or null when the cited page does not exist. */
  targetPage: number | null;
  onGoToTarget: () => void;
  onRetry: () => void;
}

function PageText({
  pages,
  pageNumber,
  citation,
  targetPage,
  onGoToTarget,
  onRetry,
}: PageTextProps) {
  if (pages.status === "error") {
    return <ErrorState compact error={pages.error} onRetry={onRetry} />;
  }
  if (pages.status !== "ready") {
    return (
      <div role="status" aria-label="Loading page text">
        <SkeletonLines lines={8} />
      </div>
    );
  }
  const page = pages.pages.find((candidate) => candidate.number === pageNumber);
  return (
    <LoadedPageText
      page={page}
      citation={citation}
      targetPage={pageNumber === targetPage ? null : targetPage}
      onGoToTarget={onGoToTarget}
    />
  );
}

interface LoadedPageTextProps {
  page: ExtractedPage | undefined;
  citation: Citation;
  /** Another page to offer ("Go to page N") when the quote is not on this one. */
  targetPage: number | null;
  onGoToTarget: () => void;
}

function LoadedPageText({ page, citation, targetPage, onGoToTarget }: LoadedPageTextProps) {
  const markRef = useRef<HTMLElement>(null);
  const text = page?.text ?? "";
  const range: TextRange | null = text ? findQuoteRange(text, citation.quote) : null;

  useEffect(() => {
    markRef.current?.scrollIntoView?.({ block: "center" });
  }, [range?.start, page?.number]);

  if (!page || !text.trim()) {
    return (
      <Notice tone="neutral">
        No text was extracted from this page.
        {page?.needsOcr ? " It appears to be scanned; OCR is not available in this version." : ""}
      </Notice>
    );
  }

  return (
    <div className="space-y-2">
      {range ? null : targetPage !== null ? (
        <Notice tone="info">
          <span>The cited passage is on page {targetPage}. </span>
          <Button size="sm" variant="ghost" className="-my-1 text-primary" onClick={onGoToTarget}>
            Go to page {targetPage}
          </Button>
        </Notice>
      ) : (
        <Notice tone={citation.status === "approximate" ? "warning" : "neutral"}>
          The quote could not be located on this page.
          {citation.status === "approximate"
            ? " Only an approximate match was found, so no passage is highlighted."
            : ""}
        </Notice>
      )}
      <div className="rounded-control border border-line bg-surface px-3 py-3 text-[13px] leading-relaxed whitespace-pre-wrap break-words text-ink">
        {range ? (
          <>
            {text.slice(0, range.start)}
            <mark ref={markRef}>{text.slice(range.start, range.end)}</mark>
            {text.slice(range.end)}
          </>
        ) : (
          text
        )}
      </div>
    </div>
  );
}
