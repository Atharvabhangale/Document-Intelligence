import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { report } from "../test/fixtures";
import {
  ApiError,
  ask,
  contentUrl,
  getCachedReport,
  getHealth,
  listWindchillDocuments,
  summarize,
  uploadDocument,
} from "./client";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastCall(): { url: string; init: RequestInit } {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) throw new Error("fetch was not called");
  return { url: String(call[0]), init: call[1] ?? {} };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("api client", () => {
  it("parses the uniform JSON error body into an ApiError", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(429, {
        error: {
          code: "ai_rate_limited",
          message: "The AI service is busy. Please try again shortly.",
          retryable: true,
          details: { retryAfter: 10 },
        },
      }),
    );
    const error = await summarize("doc-1").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 429,
      code: "ai_rate_limited",
      message: "The AI service is busy. Please try again shortly.",
      retryable: true,
      details: { retryAfter: 10 },
    });
  });

  it("maps a non-JSON 502 (proxy page) to a retryable service_unavailable error", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html><body>Bad Gateway</body></html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
    );
    const error = await getHealth().catch((caught: unknown) => caught);
    expect(error).toMatchObject({ status: 502, code: "service_unavailable", retryable: true });
  });

  it("maps a non-JSON 4xx to a non-retryable http_error", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 405 }));
    const error = await getHealth().catch((caught: unknown) => caught);
    expect(error).toMatchObject({ status: 405, code: "http_error", retryable: false });
  });

  it("maps network failures to network_error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await getHealth().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: "network_error", retryable: true });
  });

  it("reports caller cancellation as aborted and timeouts as request_timeout", async () => {
    fetchMock.mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    const controller = new AbortController();
    const pending = getHealth({ signal: controller.signal }).catch((caught: unknown) => caught);
    controller.abort();
    expect(await pending).toMatchObject({ code: "aborted" });

    vi.useFakeTimers();
    const timedOut = getHealth().catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(await timedOut).toMatchObject({ code: "request_timeout", retryable: true });
  });

  it("rejects a success response that is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html></html>", { status: 200 }));
    const error = await getHealth().catch((caught: unknown) => caught);
    expect(error).toMatchObject({ code: "invalid_response" });
  });

  it("returns null for a missing cached report but raises a missing document", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, {
        error: { code: "report_not_found", message: "No analysis exists.", retryable: false },
      }),
    );
    await expect(getCachedReport("doc-1", "summarize")).resolves.toBeNull();
    expect(lastCall().url).toBe("/api/documents/doc-1/reports/summarize");

    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, {
        error: { code: "document_not_found", message: "Not found.", retryable: false },
      }),
    );
    await expect(getCachedReport("doc-1", "summarize")).rejects.toMatchObject({
      code: "document_not_found",
    });

    fetchMock.mockResolvedValueOnce(jsonResponse(200, report));
    await expect(getCachedReport("doc-1", "summarize")).resolves.toEqual(report);
  });

  it("sends summarize with the refresh flag and ask with a JSON body", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, report)));
    await summarize("doc/1", { refresh: true });
    expect(lastCall().url).toBe("/api/documents/doc%2F1/summarize?refresh=true");
    expect(lastCall().init.method).toBe("POST");

    await summarize("doc-1");
    expect(lastCall().url).toBe("/api/documents/doc-1/summarize?refresh=false");

    await ask("doc-1", "What PPE is required?");
    expect(lastCall().url).toBe("/api/documents/doc-1/ask");
    expect(lastCall().init.body).toBe(JSON.stringify({ question: "What PPE is required?" }));
    expect(new Headers(lastCall().init.headers).get("Content-Type")).toBe("application/json");
  });

  it("uploads a file as multipart field 'file'", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: "doc-2" }));
    const file = new File(["%PDF-1.7"], "sop.pdf", { type: "application/pdf" });
    await uploadDocument(file);
    const { url, init } = lastCall();
    expect(url).toBe("/api/documents");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("only sends a search query when it is not blank", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(200, { provider: {}, items: [] })),
    );
    await listWindchillDocuments("  ");
    expect(lastCall().url).toBe("/api/windchill/documents");
    await listWindchillDocuments("LOTO B");
    expect(lastCall().url).toBe("/api/windchill/documents?q=LOTO+B");
  });

  it("builds content URLs from our API only", () => {
    expect(contentUrl("abc")).toBe("/api/documents/abc/content");
  });
});
