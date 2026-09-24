import { useCallback, useEffect, useState } from "react";

import { getHealth, isAbortError } from "./api/client";
import type { HealthResponse } from "./api/types";
import { AppBar } from "./components/AppBar";
import { DevelopmentBanner } from "./components/DevelopmentBanner";
import { DocumentWorkspace } from "./features/document/DocumentWorkspace";
import { LaunchView } from "./features/document/LaunchView";
import { HomePage } from "./features/home/HomePage";
import { parseRoute, routeToSearch, type Route } from "./lib/url";

interface NavigateOptions {
  /** Replace the current history entry (e.g. after a Windchill launch). */
  replace?: boolean;
  /** Start the analysis automatically if the document has no cached report. */
  autorun?: boolean;
}

export function App() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.search));
  // Transient intent, deliberately not in the URL: reloading the page must not re-run analysis.
  const [autorunFor, setAutorunFor] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthFailed, setHealthFailed] = useState(false);
  const [healthAttempt, setHealthAttempt] = useState(0);
  const [documentDevelopmentOnly, setDocumentDevelopmentOnly] = useState(false);

  useEffect(() => {
    const onPopState = () => {
      setRoute(parseRoute(window.location.search));
      setAutorunFor(null);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setHealthFailed(false);
    getHealth({ signal: controller.signal })
      .then((value) => {
        setHealth(value);
        setHealthFailed(false);
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setHealthFailed(true);
      });
    return () => controller.abort();
  }, [healthAttempt]);

  const retryHealth = useCallback(() => setHealthAttempt((attempt) => attempt + 1), []);

  const navigate = useCallback((next: Route, options: NavigateOptions = {}) => {
    const url = `${window.location.pathname}${routeToSearch(next)}`;
    if (options.replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
    setRoute(next);
    setAutorunFor(options.autorun && next.kind === "document" ? next.documentId : null);
    if (next.kind !== "document") setDocumentDevelopmentOnly(false);
    window.scrollTo({ top: 0 });
  }, []);

  const goHome = useCallback(() => navigate({ kind: "home" }), [navigate]);
  const openDocument = useCallback(
    (documentId: string) => navigate({ kind: "document", documentId }),
    [navigate],
  );
  const launchAutorun = route.kind === "launch" && route.autorun;
  const openLaunched = useCallback(
    (documentId: string) =>
      navigate({ kind: "document", documentId }, { replace: true, autorun: launchAutorun }),
    [navigate, launchAutorun],
  );

  const mockWindchill =
    health?.windchill.developmentOnly === true ||
    (route.kind === "document" && documentDevelopmentOnly);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-control bg-surface px-3 py-2 text-sm font-medium text-primary focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <AppBar
        health={health}
        healthFailed={healthFailed}
        onHome={goHome}
        onRetryHealth={retryHealth}
      />
      <DevelopmentBanner
        mockWindchill={mockWindchill}
        simulatedAi={health?.ai.developmentOnly === true}
      />
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-4 focus:outline-none"
      >
        {route.kind === "home" ? (
          <HomePage health={health} onOpenDocument={openDocument} />
        ) : route.kind === "launch" ? (
          <LaunchView
            key={route.reference}
            reference={route.reference}
            onOpened={openLaunched}
            onHome={goHome}
          />
        ) : (
          <DocumentWorkspace
            key={route.documentId}
            documentId={route.documentId}
            autorun={autorunFor === route.documentId}
            health={health}
            onHome={goHome}
            onDevelopmentOnlyChange={setDocumentDevelopmentOnly}
          />
        )}
      </main>
    </div>
  );
}
