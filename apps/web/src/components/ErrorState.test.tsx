import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { ErrorState } from "./ErrorState";

const CASES: [code: string, retryable: boolean, title: string, guidance: RegExp][] = [
  ["no_extractable_text", false, "No extractable text", /OCR is not available in this version/],
  ["document_too_large", false, "Document too large", /size or page count/],
  ["document_encrypted", false, "Encrypted PDF", /password-protected/],
  ["unsupported_media_type", false, "Unsupported file type", /Only PDF documents/],
  ["extraction_failed", false, "Text extraction failed", /could not be read/],
  ["document_not_found", false, "Document not found", /does not exist/],
  ["ai_rate_limited", true, "The AI service is busy", /Wait a moment/],
  ["ai_timeout", true, "The AI service did not respond in time", /Try again/],
  ["ai_unavailable", true, "The AI service is unavailable", /temporarily unavailable/],
  [
    "ai_output_invalid",
    true,
    "The AI response could not be validated",
    /No partial results are shown/,
  ],
  ["ai_output_truncated", true, "The AI response was incomplete", /No partial results are shown/],
  ["ai_refused", false, "The AI model declined this document", /administrator/],
  ["ai_not_configured", false, "AI is not configured", /administrator must configure/],
  ["ai_authentication_failed", false, "AI credentials were rejected", /administrator must check/],
  ["windchill_not_implemented", false, "Windchill connection not available", /not implemented/],
  ["content_not_available", false, "No supported content", /primary content/],
  ["network_error", true, "Cannot reach the service", /network connection/],
];

describe("ErrorState", () => {
  it.each(CASES)("maps %s to its title and guidance", (code, retryable, title, guidance) => {
    const onRetry = vi.fn();
    render(
      <ErrorState error={new ApiError(500, code, "server message", retryable)} onRetry={onRetry} />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveTextContent(guidance);
    expect(alert).toHaveTextContent(code);
    const retry = screen.queryByRole("button", { name: "Try again" });
    if (retryable) expect(retry).toBeInTheDocument();
    else expect(retry).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is used", async () => {
    const onRetry = vi.fn();
    render(
      <ErrorState error={new ApiError(429, "ai_rate_limited", "busy", true)} onRetry={onRetry} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("does not offer retry without a handler even when retryable", () => {
    render(<ErrorState error={new ApiError(504, "ai_timeout", "slow", true)} />);
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("falls back to the server's user-safe message for unknown codes", () => {
    render(
      <ErrorState
        error={new ApiError(418, "teapot_error", "The kettle is not a teapot.", false)}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).toHaveTextContent("The kettle is not a teapot.");
  });

  it("shows the server's detail for document_too_large", () => {
    render(
      <ErrorState
        error={
          new ApiError(
            413,
            "document_too_large",
            "The document has 412 pages; the limit is 300.",
            false,
          )
        }
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The document has 412 pages; the limit is 300.",
    );
  });

  it("handles non-ApiError values", () => {
    render(<ErrorState error={new Error("boom")} onRetry={() => undefined} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).not.toHaveTextContent("boom");
  });
});
