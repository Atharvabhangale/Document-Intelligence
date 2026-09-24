import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "../../api/types";
import { citations, DOCUMENT_ID, pages } from "../../test/fixtures";
import type { PagesState } from "../document/useDocumentPages";
import { SourceViewer } from "./SourceViewer";

function citation(id: string): Citation {
  const found = citations.find((c) => c.id === id);
  if (!found) throw new Error(`fixture citation ${id} missing`);
  return found;
}

const ready: PagesState = { status: "ready", pages: pages.pages };

function Harness({ initial }: { initial: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open source
      </button>
      {open ? (
        <SourceViewer
          documentId={DOCUMENT_ID}
          citation={initial}
          pageCount={5}
          pages={ready}
          onRetryPages={() => undefined}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

describe("SourceViewer", () => {
  it("shows the page text with the quote highlighted", () => {
    render(
      <SourceViewer
        documentId={DOCUMENT_ID}
        citation={citation("C18")}
        pageCount={5}
        pages={ready}
        onRetryPages={() => undefined}
        onClose={() => undefined}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "Source C18" });
    expect(dialog).toHaveTextContent("Page 3 of 5");
    const mark = dialog.querySelector("mark");
    // Matched across a line break in the extracted text.
    expect(mark?.textContent).toBe("Instruments with\nan expired calibration must not be used");
    expect(within(dialog).getByRole("link", { name: /Open PDF at page 3/ })).toHaveAttribute(
      "href",
      `/api/documents/${DOCUMENT_ID}/content#page=3`,
    );
  });

  it("opens relocated citations on the page where the quote was found", () => {
    render(
      <SourceViewer
        documentId={DOCUMENT_ID}
        citation={citation("C7")}
        pageCount={5}
        pages={ready}
        onRetryPages={() => undefined}
        onClose={() => undefined}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "Source C7" });
    expect(within(dialog).getByText("Page 4 of 5")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Relocated — found on p. 4");
    expect(dialog.querySelector("mark")).not.toBeNull();
  });

  it("says when the quote cannot be located and navigates pages", async () => {
    const user = userEvent.setup();
    render(
      <SourceViewer
        documentId={DOCUMENT_ID}
        citation={citation("C9")}
        pageCount={5}
        pages={ready}
        onRetryPages={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByText("The quote could not be located on this page.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 5 of 5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Go to page 4" }));
    expect(screen.getByText("Page 4 of 5")).toBeInTheDocument();
  });

  it("closes with Escape and returns focus to the opener", async () => {
    const user = userEvent.setup();
    render(<Harness initial={citation("C4")} />);
    const opener = screen.getByRole("button", { name: "open source" });
    await user.click(opener);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Close source viewer" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("keeps focus inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Harness initial={citation("C4")} />);
    await user.click(screen.getByRole("button", { name: "open source" }));
    const dialog = screen.getByRole("dialog");
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("shows a retry when page text fails to load", async () => {
    const onRetry = vi.fn();
    const { ApiError } = await import("../../api/client");
    render(
      <SourceViewer
        documentId={DOCUMENT_ID}
        citation={citation("C4")}
        pageCount={5}
        pages={{ status: "error", error: new ApiError(0, "network_error", "down", true) }}
        onRetryPages={onRetry}
        onClose={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
