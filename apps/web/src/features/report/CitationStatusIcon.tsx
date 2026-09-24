import { CircleCheck, FileX, MoveRight, TriangleAlert } from "lucide-react";

import type { CitationStatus } from "../../api/types";
import { cx } from "../../lib/cx";

/** "≈" drawn in the Lucide style (Lucide has no approximately-equal icon). */
function ApproximatelyEqual({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M4 9.5c1.6-1.6 3.4-1.6 5.3 0s3.7 1.6 5.4 0 3.6-1.6 5.3 0" />
      <path d="M4 15c1.6-1.6 3.4-1.6 5.3 0s3.7 1.6 5.4 0 3.6-1.6 5.3 0" />
    </svg>
  );
}

const ICONS = {
  verified: CircleCheck,
  relocated: MoveRight,
  approximate: ApproximatelyEqual,
  unverified: TriangleAlert,
  invalid_page: FileX,
} as const satisfies Record<CitationStatus, unknown>;

/** Decorative status icon; always pair it with a text label or an aria-label. */
export function CitationStatusIcon({
  status,
  className,
}: {
  status: CitationStatus;
  className?: string;
}) {
  const Icon = ICONS[status];
  return <Icon aria-hidden="true" className={cx("size-3.5 shrink-0", className)} />;
}
