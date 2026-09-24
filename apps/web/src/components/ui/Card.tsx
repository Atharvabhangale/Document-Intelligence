import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "../../lib/cx";

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("rounded-card border border-line bg-surface shadow-card", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  title: ReactNode;
  /** Heading level of the title (keeps the document outline correct). */
  level?: 2 | 3;
  description?: ReactNode;
  actions?: ReactNode;
  id?: string;
  className?: string;
}

export function CardHeader({
  title,
  level = 2,
  description,
  actions,
  id,
  className,
}: CardHeaderProps) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div
      className={cx(
        "flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-4 py-3",
        className,
      )}
    >
      <div className="min-w-0">
        <Heading id={id} className="text-sm font-semibold text-ink">
          {title}
        </Heading>
        {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
