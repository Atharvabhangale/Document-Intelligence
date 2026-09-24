import { Circle, CircleCheck, LoaderCircle } from "lucide-react";

import { Card } from "../../components/ui/Card";
import { Skeleton, SkeletonLines } from "../../components/ui/Skeleton";
import { useElapsedSeconds } from "../../hooks/useElapsedSeconds";
import { cx } from "../../lib/cx";
import { formatElapsed, pluralize } from "../../lib/format";

interface AnalysisProgressProps {
  startedAt: number;
  pageCount: number;
  model: string | null;
}

type StepState = "done" | "active" | "pending";

function Step({ state, children }: { state: StepState; children: string }) {
  const Icon = state === "done" ? CircleCheck : state === "active" ? LoaderCircle : Circle;
  const status = state === "done" ? "Done" : state === "active" ? "In progress" : "Pending";
  return (
    <li className="flex items-center gap-2">
      <Icon
        aria-hidden="true"
        className={cx(
          "size-4 shrink-0",
          state === "done" && "text-success",
          state === "active" && "animate-spin text-primary",
          state === "pending" && "text-line-strong",
        )}
      />
      <span
        className={cx(
          state === "pending" ? "text-muted" : "text-ink",
          state === "active" && "font-medium",
        )}
      >
        {children}
      </span>
      <span className="sr-only">({status})</span>
    </li>
  );
}

/**
 * Honest progress for a running analysis: an indeterminate bar, the elapsed time and the
 * pipeline steps. There is no percentage because the backend does not report one.
 */
export function AnalysisProgress({ startedAt, pageCount, model }: AnalysisProgressProps) {
  const elapsed = useElapsedSeconds(startedAt);
  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div
          role="progressbar"
          aria-label="Analyzing document"
          aria-busy="true"
          className="relative h-1 overflow-hidden bg-primary-bg"
        >
          <span className="absolute inset-y-0 left-0 w-2/5 bg-primary motion-safe:animate-indeterminate motion-reduce:w-full motion-reduce:opacity-40" />
        </div>
        <div className="space-y-3 px-4 py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[15px] font-semibold text-ink">Analyzing document</h2>
            <span className="font-mono text-sm text-muted tabular-nums">
              <span className="sr-only">Elapsed time </span>
              {formatElapsed(elapsed)}
            </span>
          </div>
          <ol className="space-y-1.5 text-sm">
            <Step state="done">
              {`Text extracted (${pageCount} ${pluralize(pageCount, "page")})`}
            </Step>
            <Step state="active">
              {model
                ? `Generating structured analysis with ${model}`
                : "Generating structured analysis"}
            </Step>
            <Step state="pending">Validating structure and verifying citations</Step>
          </ol>
          <p className="text-xs text-muted">Usually 10–40 seconds, depending on document length.</p>
          <p role="status" className="sr-only">
            Analyzing document. This usually takes 10 to 40 seconds.
          </p>
        </div>
      </Card>
      <ReportSkeleton />
    </div>
  );
}

/** Placeholder sections while a report loads or is generated. */
export function ReportSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-4">
      {[4, 3, 5].map((lines, index) => (
        <Card key={index} className="p-4">
          <Skeleton className="mb-4 h-4 w-40" />
          <SkeletonLines lines={lines} />
        </Card>
      ))}
    </div>
  );
}
