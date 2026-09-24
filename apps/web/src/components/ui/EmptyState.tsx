import type { ReactNode } from "react";

import { cx } from "../../lib/cx";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** Compact variant for use inside report sections. */
  compact?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cx(
        "flex flex-col items-center text-center",
        compact ? "gap-1.5 px-4 py-6" : "gap-2 px-6 py-10",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cx(
          "flex items-center justify-center rounded-full bg-neutral-bg text-subtle",
          compact ? "size-8 [&_svg]:size-4" : "size-10 [&_svg]:size-5",
        )}
      >
        {icon}
      </span>
      <p className={cx("font-medium text-ink", compact ? "text-sm" : "text-[15px]")}>{title}</p>
      {description ? <div className="max-w-md text-sm text-muted">{description}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
