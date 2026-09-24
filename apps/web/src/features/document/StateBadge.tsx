import { cx } from "../../lib/cx";

type StateTone = "released" | "work" | "review" | "inactive" | "unknown";

const TONE_STYLES: Record<StateTone, { badge: string; dot: string }> = {
  released: { badge: "bg-success-bg text-success", dot: "bg-success" },
  work: { badge: "bg-warning-bg text-warning", dot: "bg-warning" },
  review: { badge: "bg-info-bg text-info", dot: "bg-info" },
  inactive: { badge: "bg-neutral-bg text-muted", dot: "bg-subtle" },
  unknown: { badge: "bg-neutral-bg text-ink", dot: "bg-line-strong" },
};

/** Classify a Windchill lifecycle state name (states are configurable, so match loosely). */
export function lifecycleTone(state: string | null | undefined): StateTone {
  const value = (state ?? "").trim().toLowerCase();
  if (!value) return "unknown";
  if (value === "released") return "released";
  if (value.includes("work")) return "work";
  if (value.includes("review") || value.includes("approval")) return "review";
  if (
    ["obsolete", "cancelled", "canceled", "superseded", "withdrawn"].some((s) => value.includes(s))
  ) {
    return "inactive";
  }
  return "unknown";
}

export function isReleased(state: string | null | undefined): boolean {
  return lifecycleTone(state) === "released";
}

interface StateBadgeProps {
  state: string | null | undefined;
  className?: string;
}

/** Lifecycle state badge: colored dot plus the state name (never color alone). */
export function StateBadge({ state, className }: StateBadgeProps) {
  const tone = lifecycleTone(state);
  const styles = TONE_STYLES[tone];
  return (
    <span
      className={cx(
        "inline-flex h-5 shrink-0 items-center gap-1.5 rounded px-1.5 text-xs font-medium whitespace-nowrap",
        styles.badge,
        className,
      )}
    >
      <span aria-hidden="true" className={cx("size-1.5 rounded-full", styles.dot)} />
      {state?.trim() ? state : "No state"}
    </span>
  );
}
