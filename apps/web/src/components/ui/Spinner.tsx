import { LoaderCircle } from "lucide-react";

import { cx } from "../../lib/cx";

interface SpinnerProps {
  /** Accessible label; omit when adjacent text already describes the loading state. */
  label?: string;
  className?: string;
}

export function Spinner({ label, className }: SpinnerProps) {
  return (
    <span className={cx("inline-flex items-center", className)} role={label ? "status" : undefined}>
      <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}
