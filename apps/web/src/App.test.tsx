import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { documentRecord, DOCUMENT_ID, health, report, windchillDocuments } from "./test/fixtures";

type Handler = (init: RequestInit | undefined) => Response;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const notAnalyzed = () =>
  json(404, {
    error: { code: "report_not_found", message: "No analysis exists.", retryable: false },
  });

/** Minimal fetch router: "METHOD /path" -> handler (query string ignored). */
function mockBackend(routes: Record<string, Handler>) {
  const calls: string[] = [];
  const fetchMock = vi.fn<typeof fetch>((input, init) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    calls.push(`${key}${url.search}`);
    const handler = routes[key];
    return Promise.resolve(
      handler
        ? handler(init)
        : json(404, { error: { code: "not_found", message: key, retryable: false } }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

const docPath = `/api/documents/${DOCUMENT_ID}`;

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("App", () => {
  it("launches from a Windchill reference, imports, opens and auto-analyzes", async () => {
    window.history.replaceState(
      null,
      "",
      "/?wtRef=mock%3A%2F%2Fwtdocument%2FSOP-00123%2FA.3&autorun=1",
    );
    const calls = mockBackend({
      "GET /api/health": () => json(200, health),
      "POST /api/documents/from-windchill": () => json(201, documentRecord),
      [`GET ${docPath}`]: () => json(200, documentRecord),
      [`GET ${docPath}/reports/summarize`]: notAnalyzed,
      [`POST ${docPath}/summarize`]: () => json(200, report),
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", { level: 2, name: "Executive Summary" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe(`?doc=${DOCUMENT_ID}`);
    expect(calls).toContain(`POST ${docPath}/summarize?refresh=false`);
    expect(calls.filter((call) => call.startsWith(`POST ${docPath}/summarize`))).toHaveLength(1);
    expect(screen.getByRole("note", { name: "Development environment" })).toHaveTextContent(
      "DEVELOPMENT ONLY — Mock Windchill data. Not connected to Windchill.",
    );
    expect(screen.getByText("claude-haiku-4-5-20251001 · Anthropic")).toBeInTheDocument();
  });

  it("shows the not-analyzed state without autorun and analyzes on request", async () => {
    window.history.replaceState(null, "", `/?doc=${DOCUMENT_ID}`);
    const calls = mockBackend({
      "GET /api/health": () => json(200, health),
      [`GET ${docPath}`]: () => json(200, documentRecord),
      [`GET ${docPath}/reports/summarize`]: notAnalyzed,
      [`POST ${docPath}/summarize`]: () => json(200, report),
    });
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByText("This document has not been analyzed yet")).toBeInTheDocument();
    expect(calls.some((call) => call.startsWith(`POST ${docPath}/summarize`))).toBe(false);

    const [headerButton] = screen.getAllByRole("button", { name: "Analyze document" });
    await user.click(headerButton!);
    expect(
      await screen.findByRole("heading", { level: 2, name: "Executive Summary" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Re-analyze/ })).toBeInTheDocument();
  });

  it("opens a cached report and re-analyzes with refresh=true", async () => {
    window.history.replaceState(null, "", `/?doc=${DOCUMENT_ID}`);
    const calls = mockBackend({
      "GET /api/health": () => json(200, health),
      [`GET ${docPath}`]: () => json(200, documentRecord),
      [`GET ${docPath}/reports/summarize`]: () =>
        json(200, { ...report, provenance: { ...report.provenance, cached: true } }),
      [`POST ${docPath}/summarize`]: () =>
        json(502, {
          error: { code: "ai_output_invalid", message: "Invalid.", retryable: true },
        }),
    });
    const user = userEvent.setup();

    render(<App />);
    expect(await screen.findByText("Served from cache")).toBeInTheDocument();
    expect(screen.getByText("14 of 18 sources verified")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Re-analyze/ }));
    expect(await screen.findByText("The AI response could not be validated")).toBeInTheDocument();
    expect(calls).toContain(`POST ${docPath}/summarize?refresh=true`);
    // The previous (complete) report stays available below the error.
    expect(screen.getByText("Showing the previous analysis below.")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Executive Summary" }),
    ).toBeInTheDocument();
  });

  it("lists Windchill documents on the home page and opens one", async () => {
    mockBackend({
      "GET /api/health": () => json(200, health),
      "GET /api/windchill/documents": () => json(200, windchillDocuments),
      "GET /api/documents": () => json(200, { items: [] }),
      "POST /api/documents/from-windchill": () => json(201, documentRecord),
      [`GET ${docPath}`]: () => json(200, documentRecord),
      [`GET ${docPath}/reports/summarize`]: notAnalyzed,
    });
    const user = userEvent.setup();

    render(<App />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Select a document" }),
    ).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("SOP-00141")).toBeInTheDocument();
    expect(within(table).getByText("In Work")).toBeInTheDocument();
    expect(screen.getByText("Mock data · Development only")).toBeInTheDocument();

    await user.click(within(table).getByRole("button", { name: "Machine Maintenance SOP" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Machine Maintenance SOP" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe(`?doc=${DOCUMENT_ID}`);
  });

  it("shows a document error with a way back", async () => {
    window.history.replaceState(null, "", "/?doc=missing");
    mockBackend({
      "GET /api/health": () => json(200, health),
      "GET /api/documents/missing": () =>
        json(404, {
          error: { code: "document_not_found", message: "Not found.", retryable: false },
        }),
      "GET /api/documents/missing/reports/summarize": () =>
        json(404, {
          error: { code: "document_not_found", message: "Not found.", retryable: false },
        }),
    });
    render(<App />);
    expect(await screen.findByText("Document not found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All documents" })).toBeInTheDocument();
  });
});
