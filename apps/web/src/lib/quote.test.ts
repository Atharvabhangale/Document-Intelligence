import { describe, expect, it } from "vitest";

import { findQuoteRange } from "./quote";

function highlighted(text: string, quote: string): string | null {
  const range = findQuoteRange(text, quote);
  return range ? text.slice(range.start, range.end) : null;
}

describe("findQuoteRange", () => {
  it("finds an exact quote and returns original offsets", () => {
    const text = "Intro. The pressure shall be 55–65 bar. Outro.";
    // Edge punctuation of the quote is not part of the match (as in the backend verifier).
    const range = findQuoteRange(text, "The pressure shall be 55–65 bar.");
    expect(range).toEqual({ start: 7, end: 38 });
    expect(text.slice(7, 38)).toBe("The pressure shall be 55–65 bar");
  });

  it("ignores case", () => {
    expect(highlighted("Safety Glasses are REQUIRED.", "safety glasses are required")).toBe(
      "Safety Glasses are REQUIRED",
    );
  });

  it("ignores whitespace differences including line breaks", () => {
    const text = "Instruments with\nan expired   calibration must not be used.";
    expect(highlighted(text, "Instruments with an expired calibration must not be used.")).toBe(
      "Instruments with\nan expired   calibration must not be used",
    );
  });

  it("treats curly and straight quotes as equal", () => {
    const text = "the spindle shall be tagged “Do Not Operate” and the supervisor informed";
    expect(highlighted(text, 'tagged "Do Not Operate" and')).toBe("tagged “Do Not Operate” and");
    expect(highlighted("the operator’s lock", "the operator's lock")).toBe("the operator’s lock");
  });

  it("treats dash variants as equal", () => {
    expect(highlighted("shall be 55–65 bar", "shall be 55-65 bar")).toBe("shall be 55–65 bar");
    expect(highlighted("Rev A — released", "Rev A - released")).toBe("Rev A — released");
    expect(highlighted("range 5-8 %", "range 5−8 %")).toBe("range 5-8 %");
  });

  it("ignores surrounding quotes and punctuation of the quote", () => {
    expect(
      highlighted("Records shall be retained for 3 years.", "“Records shall be retained”"),
    ).toBe("Records shall be retained");
  });

  it("joins line-break hyphenation and maps ligatures", () => {
    const text = "Perform the preventive main-\ntenance of the ﬁlter housing.";
    expect(highlighted(text, "preventive maintenance of the filter housing")).toBe(
      "preventive main-\ntenance of the ﬁlter housing",
    );
  });

  it("keeps the hyphen variant when the word is genuinely hyphenated", () => {
    const text = "Run the pre-\nstart checks.";
    expect(highlighted(text, "pre-start checks")).toBe("pre-\nstart checks");
  });

  it("ignores invisible characters", () => {
    const text = "lock­out and tag​out";
    expect(highlighted(text, "lockout and tagout")).toBe(text);
  });

  it("spans all fragments of a quote with an ellipsis, in order", () => {
    const text = "The machine may be returned to production only when all criteria are met.";
    expect(highlighted(text, "The machine may be returned … all criteria are met")).toBe(
      "The machine may be returned to production only when all criteria are met",
    );
    expect(findQuoteRange(text, "all criteria ... The machine")).toBeNull();
  });

  it("returns null when the quote is not on the page", () => {
    expect(
      findQuoteRange("Hydraulic oil level", "Spindle runout shall not exceed 0.005 mm"),
    ).toBeNull();
    expect(findQuoteRange("", "anything")).toBeNull();
    expect(findQuoteRange("some text", "  “ ”  ")).toBeNull();
  });

  it("maps offsets correctly after astral characters", () => {
    const text = "𝐀 note: keep doors closed";
    expect(highlighted(text, "keep doors closed")).toBe("keep doors closed");
  });
});
