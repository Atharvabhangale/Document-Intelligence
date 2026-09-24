import { useCallback, useEffect, useRef, useState } from "react";

import { getPages, isAbortError, toApiError, type ApiError } from "../../api/client";
import type { ExtractedPage } from "../../api/types";

export type PagesState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; pages: ExtractedPage[] }
  | { status: "error"; error: ApiError };

/**
 * Extracted page text of a document, fetched lazily (first `load()`) and cached for the
 * lifetime of the component.
 */
export function useDocumentPages(documentId: string): { state: PagesState; load: () => void } {
  const [state, setState] = useState<PagesState>({ status: "idle" });
  const inFlight = useRef<AbortController | null>(null);
  const loaded = useRef(false);

  useEffect(
    () => () => {
      inFlight.current?.abort();
    },
    [],
  );

  const load = useCallback(() => {
    if (loaded.current || inFlight.current) return;
    const controller = new AbortController();
    inFlight.current = controller;
    setState({ status: "loading" });
    getPages(documentId, { signal: controller.signal })
      .then((result) => {
        loaded.current = true;
        setState({ status: "ready", pages: result.pages });
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        setState({ status: "error", error: toApiError(error) });
      })
      .finally(() => {
        if (inFlight.current === controller) inFlight.current = null;
      });
  }, [documentId]);

  return { state, load };
}
