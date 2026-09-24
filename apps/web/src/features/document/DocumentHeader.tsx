import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";

import { contentUrl } from "../../api/client";
import type { DocumentRecord } from "../../api/types";
import { Card } from "../../components/ui/Card";
import { Notice } from "../../components/ui/Notice";
import { Skeleton } from "../../components/ui/Skeleton";
import {
  formatBytes,
  formatDateTime,
  formatList,
  formatVersion,
  pluralize,
} from "../../lib/format";
import { isReleased, StateBadge } from "./StateBadge";

/** Human label of where the document came from. */
export function sourceLabel(record: Pick<DocumentRecord, "source" | "developmentOnly">): string {
  if (record.source === "upload")
    return record.developmentOnly ? "Uploaded file (development)" : "Uploaded file";
  return record.developmentOnly ? "Mock Windchill (development)" : "Windchill";
}

/** Notice text for pages without a usable text layer, or null when there are none. */
export function ocrNoticeText(pagesNeedingOcr: readonly number[]): string | null {
  if (pagesNeedingOcr.length === 0) return null;
  const single = pagesNeedingOcr.length === 1;
  return (
    `${single ? "Page" : "Pages"} ${formatList(pagesNeedingOcr)} ${single ? "appears" : "appear"} ` +
    `to be scanned; ${single ? "its" : "their"} content was not analyzed. ` +
    "OCR is not available in this version."
  );
}

interface DocumentHeaderProps {
  record: DocumentRecord;
  actions?: ReactNode;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 break-words text-ink">{children}</dd>
    </div>
  );
}

export function DocumentHeader({ record, actions }: DocumentHeaderProps) {
  const { metadata, content, extraction } = record;
  const version = formatVersion(metadata);
  const state = metadata.state?.trim() || null;
  const ocrText = ocrNoticeText(extraction.pagesNeedingOcr);

  return (
    <Card>
      <div className="space-y-4 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex h-5 items-center rounded border border-line-strong px-1.5 text-[11px] font-semibold tracking-wide text-muted uppercase">
                {metadata.documentType?.trim() || "Document"}
              </span>
              {metadata.number ? (
                <span className="font-mono text-sm text-ink tabular-nums">{metadata.number}</span>
              ) : null}
              {version ? (
                <span className="font-mono text-sm text-muted tabular-nums">{version}</span>
              ) : null}
              {state ? <StateBadge state={state} /> : null}
            </div>
            <h1 className="text-xl font-semibold break-words text-ink">{metadata.name}</h1>
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>

        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 border-t border-line pt-4 sm:grid-cols-2 md:grid-cols-3">
          <Field label="Revision">
            <span className="font-mono tabular-nums">{version ?? "—"}</span>
          </Field>
          <Field label="Lifecycle state">{state ? <StateBadge state={state} /> : "—"}</Field>
          <Field label="Modified">
            {metadata.modifiedDate ? (
              <>
                <time dateTime={metadata.modifiedDate}>
                  {formatDateTime(metadata.modifiedDate)}
                </time>
                {metadata.modifiedBy ? (
                  <span className="text-muted"> by {metadata.modifiedBy}</span>
                ) : null}
              </>
            ) : metadata.modifiedBy ? (
              <span className="text-muted">by {metadata.modifiedBy}</span>
            ) : record.source === "upload" ? (
              // Uploads carry no source-system dates: show when the file was uploaded instead.
              <>
                <time dateTime={record.createdAt}>{formatDateTime(record.createdAt)}</time>
                <span className="text-muted"> (uploaded)</span>
              </>
            ) : (
              "—"
            )}
          </Field>
          <Field label="Location">{metadata.location ?? "—"}</Field>
          <Field label="Primary content">
            <span className="block break-all">{content.filename}</span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5">
              <span className="whitespace-nowrap text-muted tabular-nums">
                {extraction.pageCount} {pluralize(extraction.pageCount, "page")} ·{" "}
                {formatBytes(content.sizeBytes)}
              </span>
              <a
                href={contentUrl(record.id)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex w-fit items-center gap-1 rounded text-primary underline-offset-2 hover:text-primary-hover hover:underline"
              >
                <ExternalLink aria-hidden="true" className="size-3.5" />
                Open PDF
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </span>
          </Field>
          <Field label="Source">{sourceLabel(record)}</Field>
        </dl>

        {(state && !isReleased(state)) || ocrText ? (
          <div className="space-y-2">
            {state && !isReleased(state) ? (
              <Notice tone="warning">
                This document is {state}. The analysis reflects a non-released version.
              </Notice>
            ) : null}
            {ocrText ? <Notice tone="warning">{ocrText}</Notice> : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export function DocumentHeaderSkeleton() {
  return (
    <Card aria-hidden="true" className="space-y-4 px-5 py-4">
      <div className="flex gap-2">
        <Skeleton className="h-5 w-12" />
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-5 w-16" />
      </div>
      <Skeleton className="h-6 w-2/3" />
      <div className="grid grid-cols-1 gap-3 border-t border-line pt-4 sm:grid-cols-2 md:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="space-y-1.5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-36" />
          </div>
        ))}
      </div>
    </Card>
  );
}
