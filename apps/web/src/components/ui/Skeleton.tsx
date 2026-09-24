import { cx } from "../../lib/cx";

/** Placeholder block shown while content loads (decorative; announce loading elsewhere). */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx("block rounded bg-neutral-bg motion-safe:animate-pulse", className)}
    />
  );
}

/** A few lines of text-shaped skeletons. */
export function SkeletonLines({ lines = 3, className }: { lines?: number; className?: string }) {
  const widths = ["w-full", "w-11/12", "w-4/5", "w-2/3", "w-3/4"];
  return (
    <span aria-hidden="true" className={cx("block space-y-2", className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className={cx("h-3", widths[index % widths.length])} />
      ))}
    </span>
  );
}
