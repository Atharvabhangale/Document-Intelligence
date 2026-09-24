import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { askAnswer, askUnanswerable, DOCUMENT_ID } from "../../test/fixtures";
import { AskPanel } from "./AskPanel";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

function renderPanel(onOpenCitation = vi.fn()) {
  render(
    <AskPanel
      documentId={DOCUMENT_ID}
      documentType="SOP"
      maxQuestionChars={200}
      onOpenCitation={onOpenCitation}
    />,
  );
  return {
    onOpenCitation,
    input: screen.getByRole("textbox", { name: "Question about this document" }),
  };
}

describe("AskPanel", () => {
  it("submits with Enter and renders the answer with citations", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() => jsonResponse(200, askAnswer));
    const { input, onOpenCitation } = renderPanel();

    await user.type(input, "What PPE is required?{Enter}");

    const call = fetchMock.mock.calls[0];
    expect(String(call?.[0])).toBe(`/api/documents/${DOCUMENT_ID}/ask`);
    expect(call?.[1]?.body).toBe(JSON.stringify({ question: "What PPE is required?" }));
    expect(input).toHaveValue("");

    const history = screen.getByRole("list", { name: "Questions and answers" });
    expect(await within(history).findByText(askAnswer.answer)).toBeInTheDocument();
    expect(within(history).getByText("What PPE is required?")).toBeInTheDocument();

    await user.click(within(history).getByRole("button", { name: "Source: page 2, verified" }));
    expect(onOpenCitation).toHaveBeenCalledWith(expect.objectContaining({ page: 2 }));
  });

  it("inserts a newline with Shift+Enter instead of submitting", async () => {
    const user = userEvent.setup();
    const { input } = renderPanel();
    await user.type(input, "Line one{Shift>}{Enter}{/Shift}line two");
    expect(input).toHaveValue("Line one\nline two");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("17 / 200")).toBeInTheDocument();
  });

  it("shows an unanswerable question as 'Not found in this document'", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() => jsonResponse(200, askUnanswerable));
    const { input } = renderPanel();

    await user.type(input, askUnanswerable.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Not found in this document")).toBeInTheDocument();
    expect(screen.getByText(askUnanswerable.answer)).toBeInTheDocument();
  });

  it("asks a suggested SOP question and shows errors inline with retry", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockImplementationOnce(() =>
        jsonResponse(429, {
          error: { code: "ai_rate_limited", message: "Busy.", retryable: true },
        }),
      )
      .mockImplementationOnce(() => jsonResponse(200, askAnswer));
    renderPanel();

    await user.click(screen.getByRole("button", { name: "What PPE is required?" }));
    expect(await screen.findByText("The AI service is busy")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(askAnswer.answer)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not submit blank questions and hides suggestions for non-SOP documents", async () => {
    const user = userEvent.setup();
    render(
      <AskPanel documentId={DOCUMENT_ID} documentType="Specification" onOpenCitation={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "   {Enter}");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "What PPE is required?" })).not.toBeInTheDocument();
  });
});
