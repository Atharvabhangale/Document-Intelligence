import { describe, expect, it } from "vitest";

import { report } from "../../test/fixtures";
import { buildSummaryText, reportFileName } from "./reportExport";

describe("buildSummaryText", () => {
  it("builds a plain-text summary with document identity and page references", () => {
    const text = buildSummaryText(report);
    const lines = text.split("\n");

    expect(lines.slice(0, 5)).toEqual([
      "Machine Maintenance SOP",
      "Number: SOP-00123 | Revision: A.3 | State: Released",
      "",
      "Executive summary",
      `${report.summary.executive.text} (pp. 1, 2, 5)`,
    ]);
    expect(lines.slice(5, 12)).toEqual([
      "",
      "Key points",
      "1. All work inside the enclosure or the electrical cabinet requires lockout/tagout per SOP-00087. (p. 2)",
      "2. Hydraulic pressure must be 55–65 bar and oil temperature 40–60 °C during the running checks. (p. 3)",
      "3. A drawbar clamping force below 12 kN takes the spindle out of service until the spring pack is replaced. (p. 4)",
      // Relocated citation: the page where the quote was actually found.
      "4. The hydraulic return filter is replaced every 500 operating hours of the hydraulic pump. (p. 4)",
      "5. PM records are retained for 3 years from the date of the PM. (p. 5)",
    ]);
    expect(lines.at(-1)).toMatch(
      /^AI-generated \(claude-haiku-4-5-20251001, .+\)\. Verify against the source document before use\.$/,
    );
    expect(text).not.toMatch(/<[a-z]/i);
  });

  it("omits the key points block and missing metadata gracefully", () => {
    const text = buildSummaryText({
      ...report,
      document: {
        ...report.document,
        metadata: { name: "Uploaded procedure", revision: null, iteration: null, state: null },
      },
      summary: {
        ...report.summary,
        keyPoints: [],
        executive: { text: "Summary.", citationIds: [] },
      },
    });
    expect(text.split("\n").slice(0, 5)).toEqual([
      "Uploaded procedure",
      "Revision: — | State: —",
      "",
      "Executive summary",
      "Summary.",
    ]);
    expect(text).not.toContain("Key points");
  });
});

describe("reportFileName", () => {
  it("uses number and revision.iteration", () => {
    expect(reportFileName(report)).toBe("SOP-00123_A.3_ai-report.json");
  });

  it("falls back to the document id and sanitizes unsafe characters", () => {
    expect(
      reportFileName({
        ...report,
        document: {
          ...report.document,
          documentId: "abc123",
          metadata: { name: "x", number: null, revision: "B/2", iteration: null },
        },
      }),
    ).toBe("abc123_B-2_ai-report.json");
  });
});
