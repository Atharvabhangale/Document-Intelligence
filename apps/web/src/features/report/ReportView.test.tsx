import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { emptyReport, report } from "../../test/fixtures";
import { ReportView } from "./ReportView";

function section(name: RegExp | string) {
  return screen.getByRole("region", { name });
}

describe("ReportView", () => {
  it("renders every section with counts from the report", () => {
    render(<ReportView report={report} onOpenCitation={() => undefined} showAskInNav />);

    const nav = screen.getByRole("navigation", { name: "Report sections" });
    for (const label of [
      "Summary",
      "Requirements (11)",
      "Specifications (6)",
      "Risks (4)",
      "Actions (3)",
      "Sources (18)",
      "Ask",
    ]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }

    const summary = section("Executive Summary");
    expect(within(summary).getByText("AI-generated")).toBeInTheDocument();
    expect(within(summary).getByText("Purpose")).toBeInTheDocument();
    expect(within(summary).getByText(report.summary.purpose)).toBeInTheDocument();
    expect(within(summary).getAllByRole("button", { name: /^Source:/ })).toHaveLength(3);

    expect(within(section("Key Points")).getAllByRole("listitem")).toHaveLength(5);
    expect(within(section("Requirements")).getAllByRole("row")).toHaveLength(12); // + header
    expect(
      within(section("Specifications")).getByText("Drawbar clamping force"),
    ).toBeInTheDocument();
    expect(
      within(section("Recommended Actions")).getByText(/Review before acting/),
    ).toBeInTheDocument();
    expect(
      within(section("Sources")).getAllByRole("button", { name: /^View source/ }),
    ).toHaveLength(18);
    // AI-generated tag only on the executive summary.
    expect(screen.getAllByText("AI-generated")).toHaveLength(1);
  });

  it("marks inferred items with a dashed tag and explains it", () => {
    render(<ReportView report={report} onOpenCitation={() => undefined} />);
    const table = within(section("Requirements")).getByRole("table");
    const tags = within(table).getAllByText("Inferred");
    expect(tags).toHaveLength(2);
    expect(tags[0]).toHaveAttribute(
      "title",
      "Inferred by AI — not stated verbatim in the document",
    );
  });

  it("sorts risks by severity, high first", () => {
    render(<ReportView report={report} onOpenCitation={() => undefined} />);
    const items = within(section("Risks & Concerns")).getAllByTestId("risk-item");
    expect(items.map((item) => within(item).getByRole("heading").textContent)).toEqual([
      "Hazardous stored energy during maintenance",
      "Conflicting filter replacement instructions",
      "No acceptance tolerance for spindle runout",
      "Referenced work instruction not listed",
    ]);
    expect(within(items[0]!).getByText("High")).toBeInTheDocument();
  });

  it("shows relocated sources with the page where they were found", () => {
    render(<ReportView report={report} onOpenCitation={() => undefined} />);
    expect(within(section("Sources")).getByText("Relocated — found on p. 4")).toBeInTheDocument();
  });

  it("filters requirements by mandatory and inferred", async () => {
    const user = userEvent.setup();
    render(<ReportView report={report} onOpenCitation={() => undefined} />);
    const requirements = section("Requirements");
    const filters = within(requirements).getByRole("group", { name: "Filter requirements" });

    expect(within(filters).getByRole("button", { name: "All 11" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(within(filters).getByRole("button", { name: "Mandatory 9" }));
    expect(within(requirements).getAllByRole("row")).toHaveLength(10);
    expect(within(requirements).queryByText("REQ-006")).not.toBeInTheDocument();

    await user.click(within(filters).getByRole("button", { name: "Inferred 2" }));
    const rows = within(requirements).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]?.textContent)).toEqual([
      "REQ-006",
      "REQ-010",
    ]);
  });

  it("opens a citation from any section", async () => {
    const onOpen = vi.fn();
    render(<ReportView report={report} onOpenCitation={onOpen} />);
    await userEvent.click(
      within(section("Key Points")).getByRole("button", { name: "Source: page 4, verified" }),
    );
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "C6" }));
  });

  it("collapses and expands a section", async () => {
    const user = userEvent.setup();
    render(<ReportView report={report} onOpenCitation={() => undefined} />);
    const toggle = screen.getByRole("button", { name: "Collapse Specifications" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);
    const expand = screen.getByRole("button", { name: "Expand Specifications" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Drawbar clamping force")).not.toBeVisible();
  });

  it("shows an empty state in every section when the report has no items", () => {
    render(<ReportView report={emptyReport()} onOpenCitation={() => undefined} />);
    expect(screen.getByText("No key points were identified.")).toBeInTheDocument();
    expect(
      screen.getByText("No explicit requirements were identified in this document."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No specifications or parameter values were identified in this document."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No risks or concerns were identified in this document."),
    ).toBeInTheDocument();
    expect(screen.getByText("No actions were recommended for this document.")).toBeInTheDocument();
    expect(screen.getByText("The analysis did not cite any sources.")).toBeInTheDocument();
    // The executive summary cites nothing either.
    expect(within(section("Executive Summary")).getByText("No source")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filter requirements" })).not.toBeInTheDocument();
  });
});
