import { ChevronRight } from "lucide-react";
import type { MouseEvent } from "react";

interface BreadcrumbProps {
  /** Windchill-style location, e.g. "Manufacturing SOP Library / Maintenance". */
  location: string | null | undefined;
  current: string;
  onHome: () => void;
}

export function locationSegments(location: string | null | undefined): string[] {
  return (location ?? "")
    .split(" / ")
    .map((segment) => segment.trim())
    .filter(Boolean);
}

export function Breadcrumb({ location, current, onHome }: BreadcrumbProps) {
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onHome();
  };
  const segments = locationSegments(location);
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
        <li>
          <a
            href="/"
            onClick={onClick}
            className="text-primary hover:text-primary-hover hover:underline"
          >
            All documents
          </a>
        </li>
        {segments.map((segment, index) => (
          <li key={`${index}-${segment}`} className="flex items-center gap-1">
            <ChevronRight aria-hidden="true" className="size-3.5 text-subtle" />
            <span>{segment}</span>
          </li>
        ))}
        <li className="flex min-w-0 items-center gap-1">
          <ChevronRight aria-hidden="true" className="size-3.5 text-subtle" />
          <span aria-current="page" className="truncate font-medium text-ink">
            {current}
          </span>
        </li>
      </ol>
    </nav>
  );
}
