import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { citations } from "../../test/fixtures";
import { CitationChip, CitationChips } from "./CitationChip";

function citation(id: string) {
  const found = citations.find((c) => c.id === id);
  if (!found) throw new Error(`fixture citation ${id} missing`);
  return found;
}

describe("CitationChip", () => {
  it("shows the page and an accessible label with the status", () => {
    render(<CitationChip citation={citation("C4")} onOpen={() => undefined} />);
    const chip = screen.getByRole("button", { name: "Source: page 3, verified" });
    expect(chip).toHaveTextContent("p. 3");
    expect(chip).toHaveAttribute("title", "C4 · Verified: “The pressure shall be 55–65 bar.”");
  });

  it("previews long quotes in the tooltip", () => {
    const long = { ...citation("C8"), quote: `${citation("C8").quote} `.repeat(3) };
    render(<CitationChip citation={long} onOpen={() => undefined} />);
    const title = screen.getByRole("button").getAttribute("title") ?? "";
    expect(title.startsWith("C8 · Verified: “Inspect filters regularly")).toBe(true);
    expect(title.endsWith("…”")).toBe(true);
    expect(title.length).toBeLessThan(170);
  });

  it("points relocated citations at the page where the quote was found", () => {
    render(<CitationChip citation={citation("C7")} onOpen={() => undefined} />);
    const chip = screen.getByRole("button", {
      name: "Source: page 4, relocated (cited as page 3)",
    });
    expect(chip).toHaveTextContent("p. 4");
  });

  it.each([
    ["C9", "Source: page 4, unverified"],
    ["C12", "Source: page 5, approximate"],
    ["C15", "Source: page 7, invalid page"],
  ])("labels %s with its status", (id, label) => {
    render(<CitationChip citation={citation(id)} onOpen={() => undefined} />);
    expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
  });

  it("opens the source viewer with the citation on click", async () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={citation("C2")} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: /page 2/ }));
    expect(onOpen).toHaveBeenCalledWith(citation("C2"));
  });

  it("shows a 'No source' tag when an item has no citations", () => {
    render(<CitationChips citations={[]} onOpen={() => undefined} />);
    expect(screen.getByText("No source")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
