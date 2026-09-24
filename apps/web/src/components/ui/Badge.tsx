import type { ReactNode } from "react";

import { cx } from "../../lib/cx";

export type Tone = "success" | "warning" | "danger" | "info" | "neutral" | "ai";

const SOFT: Record<Tone, string> = {
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  info: "bg-info-bg text-info",
  neutral: "bg-neutral-bg text-muted",
  ai: "bg-ai-bg text-ai",
};

const OUTLINE: Record<Tone, string> = {
  success: "border-success/40 text-success",
  warning: "border-warning/40 text-warning",
  danger: "border-danger/40 text-danger",
  info: "border-info/40 text-info",
  neutral: "border-line-strong text-muted",
  ai: "border-ai/40 text-ai",
};

interface BadgeProps {
  tone?: Tone;
  /** soft = tinted background; outline = bordered; dashed = dashed border (e.g. "Inferred"). */
  variant?: "soft" | "outline" | "dashed";
  icon?: ReactNode;
  title?: string;
  className?: string;
  children: ReactNode;
}

export function Badge({
  tone = "neutral",
  variant = "soft",
  icon,
  title,
  className,
  children,
}: BadgeProps) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded px-1.5 text-xs font-medium whitespace-nowrap",
        "[&_svg]:size-3",
        variant === "soft" ? SOFT[tone] : cx("border bg-surface", OUTLINE[tone]),
        variant === "dashed" && "border-dashed",
        className,
      )}
    >
      {icon ? (
        <span aria-hidden="true" className="contents">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}

/** Small count pill used in section headers and navigation. */
export function CountBadge({ count, className }: { count: number; className?: string }) {
  return (
    <span
      className={cx(
        "tabular-nums inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-neutral-bg px-1.5 text-xs font-medium text-muted",
        className,
      )}
    >
      {count}
    </span>
  );
}
