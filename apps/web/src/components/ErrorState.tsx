import { CircleAlert, Info, RefreshCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "../lib/cx";
import { describeError, type ErrorTone } from "../lib/errors";
import { Button } from "./ui/Button";

const TONE_STYLES: Record<ErrorTone, { box: string; icon: string; Icon: typeof Info }> = {
  danger: { box: "border-danger/25 bg-danger-bg", icon: "text-danger", Icon: CircleAlert },
  warning: { box: "border-warning-line bg-warning-bg", icon: "text-warning", Icon: TriangleAlert },
  neutral: { box: "border-line bg-surface-muted", icon: "text-muted", Icon: Info },
};

interface ErrorStateProps {
  error: unknown;
  /** Offered as a "Try again" button only when the error is retryable. */
  onRetry?: () => void;
  /** Extra actions (e.g. navigation) shown next to the retry button. */
  actions?: ReactNode;
  compact?: boolean;
  className?: string;
}

/** Maps an API error code to a title, guidance and (when retryable) a retry action. */
export function ErrorState({
  error,
  onRetry,
  actions,
  compact = false,
  className,
}: ErrorStateProps) {
  const { code, title, guidance, detail, retryable, tone } = describeError(error);
  const { box, icon, Icon } = TONE_STYLES[tone];
  const showRetry = retryable && onRetry !== undefined;
  return (
    <div
      role="alert"
      className={cx("flex gap-3 rounded-card border", box, compact ? "p-3" : "p-4", className)}
    >
      <Icon aria-hidden="true" className={cx("mt-0.5 size-5 shrink-0", icon)} />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink">{title}</p>
        <p className="mt-0.5 text-sm text-ink/90">{guidance}</p>
        {detail ? <p className="mt-1 text-sm text-muted">{detail}</p> : null}
        <p className="mt-1.5 text-xs text-muted">
          Error code: <code className="font-mono">{code}</code>
        </p>
        {showRetry || actions ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {showRetry ? (
              <Button size="sm" icon={<RefreshCw />} onClick={onRetry}>
                Try again
              </Button>
            ) : null}
            {actions}
          </div>
        ) : null}
      </div>
    </div>
  );
}
