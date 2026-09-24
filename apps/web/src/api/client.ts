/**
 * Typed client for the Document Intelligence backend (`/api`).
 *
 * The browser only ever talks to our own backend: no AI service is called from the client.
 * Every failure is raised as an {@link ApiError} with a stable `code`:
 *
 * - backend errors carry the code of the uniform error body
 *   `{"error": {"code", "message", "retryable", "details"?}}`;
 * - `network_error` — the service could not be reached;
 * - `request_timeout` — no response within the client-side timeout;
 * - `aborted` — the caller cancelled the request;
 * - `service_unavailable` / `http_error` — a non-JSON error response (e.g. from a proxy);
 * - `invalid_response` — a success response whose body is not JSON.
 */
import type {
  AskResponse,
  DocumentIntelligenceReport,
  DocumentList,
  DocumentPages,
  DocumentRecord,
  ErrorResponse,
  HealthResponse,
  WindchillDocumentList,
} from "./types";

export const API_BASE = "/api";

/** Client-side timeouts (milliseconds). */
export const TIMEOUTS = {
  /** Metadata and cached reads. */
  default: 30_000,
  /** Upload / import: includes server-side PDF text extraction. */
  ingest: 120_000,
  /** Analysis and questions: an LLM call plus validation and citation checks. */
  ai: 180_000,
} as const;

export class ApiError extends Error {
  /** HTTP status; 0 when no response was received. */
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly details: Readonly<Record<string, unknown>> | undefined;

  constructor(
    status: number,
    code: string,
    message: string,
    retryable: boolean,
    details?: Readonly<Record<string, unknown>>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.details = details;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Normalizes anything thrown by client code into an {@link ApiError}. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "client_error", "An unexpected error occurred in the application.", true);
}

export function isAbortError(error: unknown): boolean {
  return error instanceof ApiError && error.code === "aborted";
}

interface RequestOptions {
  method?: "GET" | "POST";
  query?: Record<string, string | undefined>;
  json?: unknown;
  form?: FormData;
  timeoutMs?: number;
  signal?: AbortSignal | undefined;
}

export interface CallOptions {
  signal?: AbortSignal | undefined;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) params.set(key, value);
  }
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error: unknown = body.error;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string"
  );
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const body = parseJson(await response.text());
  if (isErrorResponse(body)) {
    const { code, message, retryable, details } = body.error;
    return new ApiError(response.status, code, message, retryable === true, details ?? undefined);
  }
  // Not our uniform error body: a gateway/proxy page or an unexpected server failure.
  if (response.status >= 500) {
    return new ApiError(
      response.status,
      "service_unavailable",
      `The Document Intelligence service is not responding correctly (HTTP ${response.status}).`,
      true,
    );
  }
  return new ApiError(
    response.status,
    "http_error",
    `The server returned an unexpected response (HTTP ${response.status}).`,
    false,
  );
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, json, form, timeoutMs = TIMEOUTS.default, signal } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });

  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (form) {
    body = form; // the browser sets the multipart boundary
  } else if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  try {
    const response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body,
      signal: controller.signal,
      credentials: "same-origin",
    });
    if (!response.ok) throw await errorFromResponse(response);
    const parsed = parseJson(await response.text());
    if (parsed === undefined) {
      throw new ApiError(
        response.status,
        "invalid_response",
        "The server returned a response that could not be read.",
        true,
      );
    }
    return parsed as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) {
      throw new ApiError(0, "request_timeout", "The request did not complete in time.", true);
    }
    if (signal?.aborted) {
      throw new ApiError(0, "aborted", "The request was cancelled.", false);
    }
    throw new ApiError(0, "network_error", "The service could not be reached.", true);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }
}

const documentPath = (documentId: string) => `/documents/${encodeURIComponent(documentId)}`;

// --- Endpoints ------------------------------------------------------------------------------

export function getHealth(options: CallOptions = {}): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal: options.signal });
}

/** Browse/search the (mock) Windchill document source. */
export function listWindchillDocuments(
  q?: string,
  options: CallOptions = {},
): Promise<WindchillDocumentList> {
  const query = q?.trim();
  return request<WindchillDocumentList>("/windchill/documents", {
    query: { q: query ? query : undefined },
    signal: options.signal,
  });
}

/** Register a document from the Windchill provider (fetches content and extracts text). */
export function importFromWindchill(
  reference: string,
  options: CallOptions = {},
): Promise<DocumentRecord> {
  return request<DocumentRecord>("/documents/from-windchill", {
    method: "POST",
    json: { reference },
    timeoutMs: TIMEOUTS.ingest,
    signal: options.signal,
  });
}

/** Upload a PDF (multipart field `file`) for development testing. */
export function uploadDocument(file: File, options: CallOptions = {}): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<DocumentRecord>("/documents", {
    method: "POST",
    form,
    timeoutMs: TIMEOUTS.ingest,
    signal: options.signal,
  });
}

export function listDocuments(options: CallOptions = {}): Promise<DocumentList> {
  return request<DocumentList>("/documents", { signal: options.signal });
}

export function getDocument(
  documentId: string,
  options: CallOptions = {},
): Promise<DocumentRecord> {
  return request<DocumentRecord>(documentPath(documentId), { signal: options.signal });
}

export function getPages(documentId: string, options: CallOptions = {}): Promise<DocumentPages> {
  return request<DocumentPages>(`${documentPath(documentId)}/pages`, { signal: options.signal });
}

/**
 * The cached report for `task`, or `null` when the document has not been analyzed yet
 * (HTTP 404). A missing *document* is still raised as `document_not_found`.
 */
export async function getCachedReport(
  documentId: string,
  task: "summarize",
  options: CallOptions = {},
): Promise<DocumentIntelligenceReport | null> {
  try {
    return await request<DocumentIntelligenceReport>(
      `${documentPath(documentId)}/reports/${task}`,
      {
        signal: options.signal,
      },
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.code !== "document_not_found") {
      return null;
    }
    throw error;
  }
}

export interface SummarizeOptions extends CallOptions {
  /** Ignore a cached report and run the analysis again. */
  refresh?: boolean;
}

export function summarize(
  documentId: string,
  options: SummarizeOptions = {},
): Promise<DocumentIntelligenceReport> {
  return request<DocumentIntelligenceReport>(`${documentPath(documentId)}/summarize`, {
    method: "POST",
    query: { refresh: options.refresh ? "true" : "false" },
    timeoutMs: TIMEOUTS.ai,
    signal: options.signal,
  });
}

export function ask(
  documentId: string,
  question: string,
  options: CallOptions = {},
): Promise<AskResponse> {
  return request<AskResponse>(`${documentPath(documentId)}/ask`, {
    method: "POST",
    json: { question },
    timeoutMs: TIMEOUTS.ai,
    signal: options.signal,
  });
}

/** URL of the document's primary content (PDF), served by our backend. */
export function contentUrl(documentId: string): string {
  return `${API_BASE}${documentPath(documentId)}/content`;
}
