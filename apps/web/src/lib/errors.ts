/**
 * User-facing copy for API error codes (see apps/api/src/docintel/core/errors.py and
 * src/api/client.ts for the client-side codes).
 */
import { ApiError, toApiError } from "../api/client";

export type ErrorTone = "danger" | "warning" | "neutral";

export interface ErrorDescription {
  code: string;
  title: string;
  guidance: string;
  /** The backend's message when it adds specifics to the guidance (e.g. the size limit). */
  detail: string | null;
  retryable: boolean;
  tone: ErrorTone;
}

interface ErrorCopy {
  title: string;
  guidance: string;
  tone?: ErrorTone;
  /** Show the backend's (user-safe) message as a detail line. */
  showMessage?: boolean;
}

const ADMIN_GUIDANCE = "Contact your administrator.";

const ERROR_COPY: Readonly<Record<string, ErrorCopy>> = {
  // Documents and extraction
  no_extractable_text: {
    title: "No extractable text",
    guidance:
      "The PDF has no text layer — it is probably a scanned image. OCR is not available in this " +
      "version, so the document cannot be analyzed.",
    tone: "warning",
  },
  document_too_large: {
    title: "Document too large",
    guidance: "The document exceeds the file size or page count supported by this version.",
    tone: "warning",
    showMessage: true,
  },
  document_encrypted: {
    title: "Encrypted PDF",
    guidance:
      "The PDF is encrypted or password-protected and cannot be read. Provide an unprotected " +
      "copy of the document.",
    tone: "warning",
  },
  unsupported_media_type: {
    title: "Unsupported file type",
    guidance: "Only PDF documents are supported in this version.",
    tone: "warning",
  },
  extraction_failed: {
    title: "Text extraction failed",
    guidance: "The PDF could not be read. It may be damaged or use an unsupported structure.",
  },
  document_not_found: {
    title: "Document not found",
    guidance: "The document does not exist or is no longer available.",
    tone: "neutral",
  },
  not_found: {
    title: "Not found",
    guidance: "The requested resource was not found.",
    tone: "neutral",
  },
  invalid_request: {
    title: "Invalid request",
    guidance: "The request could not be processed. Check the input and try again.",
    tone: "warning",
    showMessage: true,
  },
  access_denied: {
    title: "Access denied",
    guidance: "You do not have permission to access this document's content.",
  },
  // Windchill
  windchill_not_implemented: {
    title: "Windchill connection not available",
    guidance:
      "The connection to Windchill is not implemented in this version. Documents are served by " +
      "the development mock provider only.",
    tone: "neutral",
  },
  windchill_provider_error: {
    title: "Document source unavailable",
    guidance: "The document source could not be reached. Try again in a moment.",
  },
  content_not_available: {
    title: "No supported content",
    guidance: "The document has no primary content in a supported format (PDF).",
    tone: "warning",
  },
  // AI
  ai_rate_limited: {
    title: "The AI service is busy",
    guidance: "Too many requests are being processed right now. Wait a moment and try again.",
    tone: "warning",
  },
  ai_timeout: {
    title: "The AI service did not respond in time",
    guidance: "Large documents can take longer to analyze. Try again.",
    tone: "warning",
  },
  ai_unavailable: {
    title: "The AI service is unavailable",
    guidance: "The AI service is temporarily unavailable. Try again in a few minutes.",
    tone: "warning",
  },
  ai_provider_error: {
    title: "The AI service returned an error",
    guidance: "The request to the AI service failed. Try again.",
  },
  ai_output_invalid: {
    title: "The AI response could not be validated",
    guidance:
      "The response did not match the required structure, even after an automatic repair " +
      "attempt. No partial results are shown.",
  },
  ai_output_truncated: {
    title: "The AI response was incomplete",
    guidance:
      "The response was cut off before it was complete. No partial results are shown. Very long " +
      "documents may exceed the output limit.",
  },
  ai_refused: {
    title: "The AI model declined this document",
    guidance: `The model declined to process the content. ${ADMIN_GUIDANCE}`,
    tone: "warning",
  },
  ai_not_configured: {
    title: "AI is not configured",
    guidance:
      "No AI provider is configured on the server. An administrator must configure the AI " +
      "provider and its credentials before documents can be analyzed.",
    tone: "warning",
  },
  ai_authentication_failed: {
    title: "AI credentials were rejected",
    guidance:
      "The AI service rejected the credentials configured on the server. An administrator must " +
      "check the AI provider's API key.",
    tone: "warning",
  },
  // Client-side
  network_error: {
    title: "Cannot reach the service",
    guidance:
      "The Document Intelligence service could not be reached. Check your network connection and " +
      "that the service is running.",
  },
  request_timeout: {
    title: "The request timed out",
    guidance: "The service did not respond in time. Try again.",
    tone: "warning",
  },
  service_unavailable: {
    title: "Service unavailable",
    guidance: "The Document Intelligence service is not responding correctly. Try again shortly.",
  },
  invalid_response: {
    title: "Unexpected response",
    guidance: "The service returned a response that could not be read. Try again.",
  },
  internal_error: {
    title: "Unexpected server error",
    guidance: "An unexpected error occurred on the server. Try again later.",
  },
};

const FALLBACK: ErrorCopy = {
  title: "Something went wrong",
  guidance: "An unexpected error occurred.",
};

export function describeError(error: unknown): ErrorDescription {
  const apiError: ApiError = toApiError(error);
  const copy = ERROR_COPY[apiError.code];
  return {
    code: apiError.code,
    title: copy?.title ?? FALLBACK.title,
    // Unknown codes: the backend message is user-safe by contract (no secrets or document text).
    guidance: copy?.guidance ?? (apiError.message || FALLBACK.guidance),
    detail: copy?.showMessage && apiError.message !== copy.guidance ? apiError.message : null,
    retryable: apiError.retryable,
    tone: copy?.tone ?? "danger",
  };
}
