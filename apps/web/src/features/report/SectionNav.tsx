import { cx } from "../../lib/cx";

export interface NavItem {
  /** Target section id. */
  id: string;
  label: string;
  count?: number;
  /** Other section ids that highlight this item (e.g. Key Points → Summary). */
  alsoActiveFor?: readonly string[];
}

interface SectionNavProps {
  items: readonly NavItem[];
  activeId: string | null;
  onNavigate: (id: string) => void;
}

/**
 * Sticky in-page navigation (horizontally scrollable on narrow screens).
 *
 * The sticky wrapper carries a strip of page background above the bar so that content
 * scrolling underneath never shows between the bar and the top of the viewport. It is pulled
 * up by the same amount (`-mt-2 pt-2`) so the bar keeps its place in the layout.
 */
export function SectionNav({ items, activeId, onNavigate }: SectionNavProps) {
  return (
    <div className="sticky top-0 z-20 -mx-4 -mt-2 bg-canvas pt-2 sm:mx-0">
      <nav
        aria-label="Report sections"
        className="border-b border-line px-4 sm:rounded-card sm:border sm:bg-surface sm:px-1 sm:shadow-card"
      >
        <ul className="scrollbar-none flex gap-0.5 overflow-x-auto py-1">
          {items.map((item) => {
            const active =
              item.id === activeId || (activeId !== null && item.alsoActiveFor?.includes(activeId));
            return (
              <li key={item.id} className="shrink-0">
                <a
                  href={`#${item.id}`}
                  aria-current={active ? "location" : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    onNavigate(item.id);
                  }}
                  className={cx(
                    "tabular-nums flex h-8 items-center gap-1 rounded-control px-2.5 text-sm whitespace-nowrap transition-colors",
                    active
                      ? "bg-primary-bg font-medium text-primary"
                      : "text-muted hover:bg-neutral-bg hover:text-ink",
                  )}
                >
                  {item.label}
                  {item.count !== undefined ? " " : null}
                  {item.count !== undefined ? (
                    <span className={cx("text-xs", active ? "text-primary" : "text-muted")}>
                      ({item.count})
                    </span>
                  ) : null}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
