import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { CountBadge } from "../../components/ui/Badge";
import { cx } from "../../lib/cx";

interface SectionCardProps {
  /** DOM id of the section (anchor target of the section navigation). */
  id: string;
  title: string;
  count?: number;
  /** Extra header content (e.g. the "AI-generated" tag). */
  badge?: ReactNode;
  /** Controls rendered on the right of the header (before the collapse button). */
  toolbar?: ReactNode;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/** A report section: card with a header, count, collapse control and body. */
export function SectionCard({
  id,
  title,
  count,
  badge,
  toolbar,
  collapsed,
  onToggle,
  children,
  footer,
}: SectionCardProps) {
  const headingId = `${id}-heading`;
  const showToolbar = Boolean(toolbar) && !collapsed;
  const bodyId = `${id}-body`;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className="scroll-mt-16 rounded-card border border-line bg-surface shadow-card"
    >
      <div
        className={cx(
          "flex flex-wrap items-center gap-2 px-4 py-2.5",
          !collapsed && "border-b border-line",
        )}
      >
        <h2 id={headingId} tabIndex={-1} className="text-[15px] font-semibold text-ink">
          {title}
        </h2>
        {count !== undefined ? <CountBadge count={count} /> : null}
        {badge}
        {showToolbar ? (
          // Own row on narrow screens, inline before the collapse button from `sm`.
          <div className="order-last w-full sm:order-none sm:ml-auto sm:w-auto">{toolbar}</div>
        ) : null}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          aria-label={`${collapsed ? "Expand" : "Collapse"} ${title}`}
          title={collapsed ? "Expand" : "Collapse"}
          className={cx(
            "ml-auto flex size-7 items-center justify-center rounded-control text-muted hover:bg-neutral-bg hover:text-ink",
            showToolbar && "sm:ml-0",
          )}
        >
          <ChevronDown
            aria-hidden="true"
            className={cx("size-4 transition-transform", collapsed && "-rotate-90")}
          />
        </button>
      </div>
      <div id={bodyId} hidden={collapsed}>
        {children}
        {footer}
      </div>
    </section>
  );
}
