import { useEffect, useState } from "react";

/**
 * The id of the section currently at the top of the viewport (for navigation highlighting).
 * Falls back to the first id when IntersectionObserver is unavailable.
 */
export function useActiveSection(ids: readonly string[], topOffset = 72): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);
  const key = ids.join("|");

  useEffect(() => {
    const sectionIds = key ? key.split("|") : [];
    if (typeof IntersectionObserver === "undefined" || sectionIds.length === 0) return;
    const visible = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) visible.set(entry.target.id, entry.isIntersecting);
        const first = sectionIds.find((id) => visible.get(id));
        if (first) setActive(first);
      },
      // A band just below the sticky navigation: the first section crossing it is active.
      { rootMargin: `-${topOffset}px 0px -55% 0px`, threshold: 0 },
    );
    for (const id of sectionIds) {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [key, topOffset]);

  return active;
}
