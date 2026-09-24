/**
 * URL-based routing (query parameters only; no router dependency).
 *
 * - `/`                           Home — select a document.
 * - `?doc=<documentId>`           Document workspace.
 * - `?wtRef=<reference>&autorun=1` Launch from a Windchill action (simulated in development):
 *                                 import the document, open it and, with `autorun=1`, start the
 *                                 analysis when no cached report exists.
 */

export type Route =
  | { kind: "home" }
  | { kind: "document"; documentId: string }
  | { kind: "launch"; reference: string; autorun: boolean };

const TRUE_VALUES = new Set(["1", "true", "yes"]);

export function parseRoute(search: string): Route {
  const params = new URLSearchParams(search);
  const reference = params.get("wtRef")?.trim();
  if (reference) {
    const autorun = TRUE_VALUES.has((params.get("autorun") ?? "").toLowerCase());
    return { kind: "launch", reference, autorun };
  }
  const documentId = params.get("doc")?.trim();
  if (documentId) return { kind: "document", documentId };
  return { kind: "home" };
}

/** Query string (with leading "?", or "" for home) for a route. */
export function routeToSearch(route: Route): string {
  const params = new URLSearchParams();
  switch (route.kind) {
    case "home":
      return "";
    case "document":
      params.set("doc", route.documentId);
      break;
    case "launch":
      params.set("wtRef", route.reference);
      if (route.autorun) params.set("autorun", "1");
      break;
  }
  return `?${params.toString()}`;
}

/** Link to a PDF page using the standard `#page=N` open parameter of browser PDF viewers. */
export function pdfPageUrl(contentUrl: string, page: number): string {
  return `${contentUrl}#page=${page}`;
}
