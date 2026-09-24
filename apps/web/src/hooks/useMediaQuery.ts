import { useCallback, useSyncExternalStore } from "react";

/** Subscribe to a CSS media query (e.g. "(min-width: 768px)"). */
export function useMediaQuery(query: string, fallback = true): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return () => undefined;
      }
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  const getSnapshot = () =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : fallback;
  return useSyncExternalStore(subscribe, getSnapshot, () => fallback);
}

/** Tailwind's `md` breakpoint: tables above, stacked cards below. */
export function useIsWide(): boolean {
  return useMediaQuery("(min-width: 768px)");
}
