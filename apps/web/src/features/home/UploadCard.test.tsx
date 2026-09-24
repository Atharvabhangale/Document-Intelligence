import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { documentRecord } from "../../test/fixtures";
import { UploadCard, validatePdf } from "./UploadCard";

function pdf(name = "sop.pdf", size = 2048, type = "application/pdf"): File {
  const file = new File(["%PDF-1.7"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("validatePdf", () => {
  it("accepts PDFs within the size limit", () => {
    expect(validatePdf(pdf(), 25)).toBeNull();
    // Some systems report no MIME type: the extension is enough.
    expect(validatePdf(pdf("SOP.PDF", 2048, ""), 25)).toBeNull();
  });

  it("explains why a file is rejected", () => {
    expect(validatePdf(pdf("notes.txt", 10, "text/plain"), 25)).toBe(
      "“notes.txt” is not a PDF. Only PDF documents are supported.",
    );
    expect(validatePdf(pdf("empty.pdf", 0), 25)).toBe("“empty.pdf” is empty.");
    expect(validatePdf(pdf("big.pdf", 30 * 1024 * 1024), 25)).toBe(
      "“big.pdf” is 30 MB. The maximum size is 25 MB.",
    );
  });
});

describe("UploadCard", () => {
  it("shows the limits and uploads a valid file", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(documentRecord), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const onUploaded = vi.fn();
    const user = userEvent.setup();
    render(<UploadCard maxUploadMb={25} maxPages={300} onUploaded={onUploaded} />);

    expect(screen.getByText("PDF only · up to 25 MB · 300 pages")).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Choose a PDF file to upload"), pdf());
    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalledWith(documentRecord.id));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/documents");
  });

  it("rejects an oversized file without uploading it", async () => {
    const user = userEvent.setup({ applyAccept: false });
    render(<UploadCard maxUploadMb={1} onUploaded={vi.fn()} />);
    await user.upload(
      screen.getByLabelText("Choose a PDF file to upload"),
      pdf("big.pdf", 2 * 1024 * 1024),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("The maximum size is 1 MB.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps a scanned PDF to the no_extractable_text guidance", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "no_extractable_text",
            message: "The document has no extractable text layer.",
            retryable: false,
          },
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    );
    const user = userEvent.setup();
    render(<UploadCard maxUploadMb={25} onUploaded={vi.fn()} />);
    await user.upload(screen.getByLabelText("Choose a PDF file to upload"), pdf("scan.pdf"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No extractable text");
    expect(alert).toHaveTextContent("OCR is not available in this version");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
