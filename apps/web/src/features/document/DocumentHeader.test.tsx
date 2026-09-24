import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DocumentRecord } from "../../api/types";
import { documentRecord } from "../../test/fixtures";
import { DocumentHeader, ocrNoticeText } from "./DocumentHeader";

function withChanges(changes: {
  state?: string | null;
  pagesNeedingOcr?: number[];
  source?: DocumentRecord["source"];
}): DocumentRecord {
  return {
    ...documentRecord,
    source: changes.source ?? documentRecord.source,
    metadata: {
      ...documentRecord.metadata,
      state: changes.state === undefined ? documentRecord.metadata.state : changes.state,
    },
    extraction: {
      ...documentRecord.extraction,
      pagesNeedingOcr: changes.pagesNeedingOcr ?? documentRecord.extraction.pagesNeedingOcr,
    },
  };
}

describe("DocumentHeader", () => {
  it("shows Windchill metadata, never taken from the AI", () => {
    render(<DocumentHeader record={documentRecord} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Machine Maintenance SOP" }),
    ).toBeInTheDocument();
    expect(screen.getByText("SOP-00123")).toBeInTheDocument();
    expect(screen.getByText("SOP")).toBeInTheDocument();
    expect(screen.getAllByText("A.3").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Released").length).toBeGreaterThan(0);
    expect(screen.getByText(/by J\. Alvarez/)).toBeInTheDocument();
    expect(screen.getByText("Manufacturing SOP Library / Maintenance")).toBeInTheDocument();
    expect(screen.getByText("Mock Windchill (development)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open PDF/ })).toHaveAttribute(
      "href",
      `/api/documents/${documentRecord.id}/content`,
    );
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("warns when the document is not Released", () => {
    render(<DocumentHeader record={withChanges({ state: "In Work" })} />);
    expect(screen.getByRole("note")).toHaveTextContent(
      "This document is In Work. The analysis reflects a non-released version.",
    );
  });

  it("does not warn when there is no lifecycle state", () => {
    render(<DocumentHeader record={withChanges({ state: null, source: "upload" })} />);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByText("Uploaded file (development)")).toBeInTheDocument();
  });

  it("lists pages that need OCR", () => {
    render(<DocumentHeader record={withChanges({ pagesNeedingOcr: [3] })} />);
    expect(screen.getByRole("note")).toHaveTextContent(
      "Page 3 appears to be scanned; its content was not analyzed. OCR is not available in this version.",
    );
  });

  it("formats several OCR pages", () => {
    expect(ocrNoticeText([3, 5, 7])).toBe(
      "Pages 3, 5 and 7 appear to be scanned; their content was not analyzed. OCR is not available in this version.",
    );
    expect(ocrNoticeText([])).toBeNull();
  });
});
