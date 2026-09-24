import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { documentRecord, windchillDocuments } from "../../test/fixtures";
import { WindchillDocumentsCard } from "./WindchillDocumentsCard";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Report every `min-width` media query as (not) matching. */
function setViewportWide(wide: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: query.includes("min-width") ? wide : false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("WindchillDocumentsCard", () => {
  it("lists documents in a table and opens one", async () => {
    setViewportWide(true);
    fetchMock.mockImplementation((_input, init) =>
      Promise.resolve(
        init?.method === "POST" ? json(201, documentRecord) : json(200, windchillDocuments),
      ),
    );
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<WindchillDocumentsCard onOpen={onOpen} />);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3); // header + 2 documents
    expect(within(rows[1]!).getByText("SOP-00123")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("A.3")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("In Work")).toBeInTheDocument();

    await user.click(within(table).getByRole("button", { name: "Machine Maintenance SOP" }));
    expect(onOpen).toHaveBeenCalledWith(documentRecord.id);
    const importCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(importCall?.[1]?.body).toBe(
      JSON.stringify({ reference: "mock://wtdocument/SOP-00123/A.3" }),
    );
  });

  it("renders a stacked list on phones", async () => {
    setViewportWide(false);
    fetchMock.mockImplementation(() => Promise.resolve(json(200, windchillDocuments)));
    render(<WindchillDocumentsCard onOpen={vi.fn()} />);

    const item = await screen.findByRole("button", { name: /Hydraulic Press Setup/ });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(item).toHaveTextContent("SOP-00141");
    expect(item).toHaveTextContent("A.1");
    expect(item).toHaveTextContent("In Work");
    expect(item).toHaveTextContent("Manufacturing SOP Library / Production");
  });

  it("shows an import error with a retry", async () => {
    setViewportWide(true);
    fetchMock.mockImplementation((_input, init) =>
      Promise.resolve(
        init?.method === "POST"
          ? json(501, {
              error: {
                code: "windchill_provider_error",
                message: "The document source could not be reached.",
                retryable: true,
              },
            })
          : json(200, windchillDocuments),
      ),
    );
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<WindchillDocumentsCard onOpen={onOpen} />);

    await user.click(await screen.findByRole("button", { name: "Machine Maintenance SOP" }));
    expect(await screen.findByText("Document source unavailable")).toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled();

    fetchMock.mockImplementation(() => Promise.resolve(json(201, documentRecord)));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(onOpen).toHaveBeenCalledWith(documentRecord.id));
  });

  it("keeps the previous results visible while a search runs", async () => {
    setViewportWide(true);
    let resolveSearch: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation((input) => {
      if (String(input).includes("q=")) {
        return new Promise<Response>((resolve) => {
          resolveSearch = resolve;
        });
      }
      return Promise.resolve(json(200, windchillDocuments));
    });
    const user = userEvent.setup();
    render(<WindchillDocumentsCard onOpen={vi.fn()} />);
    await screen.findByRole("table");

    await user.type(screen.getByRole("searchbox"), "press");
    await vi.waitFor(() => expect(resolveSearch).toBeDefined());
    // Still showing the unfiltered list, with a busy indicator in the search field.
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByRole("status")).toHaveTextContent("Searching");

    resolveSearch?.(json(200, { ...windchillDocuments, items: windchillDocuments.items.slice(1) }));
    await vi.waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(2));
    expect(screen.queryByText("Searching")).not.toBeInTheDocument();
  });
});
