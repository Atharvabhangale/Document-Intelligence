import { Database, ShieldAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type {
  DocumentIntelligenceReport,
  DocumentRecord,
  VerificationSummary,
} from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Card, CardHeader } from "../../components/ui/Card";
import { cx } from "../../lib/cx";
import {
  formatDateTime,
  formatDuration,
  formatList,
  formatNumber,
  formatRelativeTime,
  providerLabel,
} from "../../lib/format";

interface AnalysisRailProps {
  record: DocumentRecord;
  report: DocumentIntelligenceReport | null;
}

/** Right rail: analysis provenance, text coverage, warnings, limitations and the disclaimer. */
export function AnalysisRail({ record, report }: AnalysisRailProps) {
  const warnings = [
    ...new Set([...(report?.warnings ?? []), ...(record.extraction.warnings ?? [])]),
  ];
  const limitations = report?.limitations ?? [];
  return (
    <div className="space-y-4">
      {report ? <AnalysisCard report={report} /> : null}
      <CoverageCard record={record} />
      {warnings.length > 0 ? (
        <Card className="border-warning-line">
          <CardHeader title="Warnings" className="border-warning-line bg-warning-bg" />
          <ul className="space-y-2 px-4 py-3 text-sm">
            {warnings.map((warning) => (
              <li key={warning} className="flex gap-2">
                <TriangleAlert
                  aria-hidden="true"
                  className="mt-0.5 size-3.5 shrink-0 text-warning"
                />
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {limitations.length > 0 ? (
        <Card>
          <CardHeader title="Limitations noted by the AI" />
          <ul className="list-disc space-y-1.5 py-3 pr-4 pl-8 text-sm text-ink/90 marker:text-subtle">
            {limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </Card>
      ) : null}
      <p className="flex gap-2 rounded-card border border-line bg-surface-muted px-3 py-2.5 text-xs text-muted">
        <ShieldAlert aria-hidden="true" className="mt-px size-4 shrink-0 text-subtle" />
        <span>
          AI-generated content. Verify against the source document before use. Sources marked
          Verified were matched to the document text automatically.
        </span>
      </p>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 text-right break-words text-ink">{children}</dd>
    </div>
  );
}

function AnalysisCard({ report }: { report: DocumentIntelligenceReport }) {
  const { provenance, verification } = report;
  const { inputTokens, outputTokens } = provenance.usage;
  return (
    <Card>
      <CardHeader
        title="Analysis"
        actions={
          provenance.cached ? (
            <Badge
              tone="info"
              icon={<Database />}
              title="This report was served from the analysis cache."
            >
              Served from cache
            </Badge>
          ) : null
        }
      />
      <div className="space-y-3 px-4 py-3">
        <VerificationMeter verification={verification} />
        <dl className="divide-y divide-line/70 text-sm">
          <Row label="Model">
            <span className="font-mono text-xs">{provenance.model}</span>
          </Row>
          <Row label="Provider">{providerLabel(provenance.provider)}</Row>
          <Row label="Prompt">
            {provenance.promptId} v{provenance.promptVersion}
          </Row>
          <Row label="Generated">
            <time dateTime={provenance.generatedAt} title={formatDateTime(provenance.generatedAt)}>
              {formatRelativeTime(provenance.generatedAt)}
            </time>
          </Row>
          <Row label="Duration">
            <span className="tabular-nums">{formatDuration(provenance.durationMs)}</span>
          </Row>
          <Row label="Tokens">
            <span className="tabular-nums">
              {formatNumber(inputTokens)} in · {formatNumber(outputTokens)} out
            </span>
          </Row>
          {provenance.attempts > 1 ? (
            <Row label="Attempts">
              <span className="tabular-nums">
                {provenance.attempts} ({provenance.attempts - 1} automatic repair)
              </span>
            </Row>
          ) : null}
          <Row label="Versions">
            <span className="tabular-nums">
              pipeline {provenance.pipelineVersion} · schema{" "}
              {provenance.schemaVersion ?? report.schemaVersion ?? "1.0"}
            </span>
          </Row>
          <Row label="Extractor">
            <span className="font-mono text-xs">{provenance.extractor}</span>
          </Row>
        </dl>
      </div>
    </Card>
  );
}

const SEGMENTS: { key: keyof VerificationSummary; label: string; className: string }[] = [
  { key: "verified", label: "Verified", className: "bg-success" },
  { key: "relocated", label: "Relocated", className: "bg-info" },
  { key: "approximate", label: "Approximate", className: "bg-warning" },
  { key: "unverified", label: "Unverified", className: "bg-danger" },
  { key: "invalidPage", label: "Invalid page", className: "bg-danger/60" },
];

export function VerificationMeter({ verification }: { verification: VerificationSummary }) {
  const total = verification.totalCitations;
  const present = SEGMENTS.filter((segment) => verification[segment.key] > 0);
  return (
    <div>
      <p className="text-sm font-medium text-ink tabular-nums">
        {total === 0 ? "No sources cited" : `${verification.verified} of ${total} sources verified`}
      </p>
      <div
        role="img"
        aria-label={
          total === 0
            ? "No sources cited"
            : present.map((s) => `${verification[s.key]} ${s.label.toLowerCase()}`).join(", ")
        }
        className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-neutral-bg"
      >
        {present.map((segment) => (
          <span
            key={segment.key}
            className={cx("h-full", segment.className)}
            style={{ width: `${(verification[segment.key] / total) * 100}%` }}
          />
        ))}
      </div>
      {present.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
          {present.map((segment) => (
            <li key={segment.key} className="flex items-center gap-1.5 tabular-nums">
              <span aria-hidden="true" className={cx("size-2 rounded-full", segment.className)} />
              {segment.label} {verification[segment.key]}
            </li>
          ))}
        </ul>
      ) : null}
      {verification.itemsWithoutVerifiedSource > 0 ? (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-warning">
          <TriangleAlert aria-hidden="true" className="mt-px size-3.5 shrink-0" />
          {verification.itemsWithoutVerifiedSource} of {verification.itemsTotal} items have no
          verified source.
        </p>
      ) : null}
    </div>
  );
}

function CoverageCard({ record }: { record: DocumentRecord }) {
  const { pageCount, pagesWithText, pagesNeedingOcr } = record.extraction;
  return (
    <Card>
      <CardHeader title="Text coverage" />
      <dl className="divide-y divide-line/70 px-4 py-2 text-sm">
        <Row label="Pages">
          <span className="tabular-nums">{formatNumber(pageCount)}</span>
        </Row>
        <Row label="Pages with text">
          <span className="tabular-nums">{formatNumber(pagesWithText)}</span>
        </Row>
        <Row label="Pages needing OCR">
          {pagesNeedingOcr.length === 0 ? (
            <span className="tabular-nums">None</span>
          ) : (
            <span className="text-warning tabular-nums">
              {pagesNeedingOcr.length} (p. {formatList(pagesNeedingOcr)})
            </span>
          )}
        </Row>
      </dl>
    </Card>
  );
}
