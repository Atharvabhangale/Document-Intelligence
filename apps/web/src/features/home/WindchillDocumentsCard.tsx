import { FolderOpen, Search } from "lucide-react";
import { useEffect, useId, useState } from "react";

import {
  importFromWindchill,
  isAbortError,
  listWindchillDocuments,
  toApiError,
  type ApiError,
} from "../../api/client";
import type { WindchillDocument, WindchillDocumentList } from "../../api/types";
import { ErrorState } from "../../components/ErrorState";
import { Badge } from "../../components/ui/Badge";
import { Card, CardHeader } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { Spinner } from "../../components/ui/Spinner";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { cx } from "../../lib/cx";
import { formatDate, formatVersion } from "../../lib/format";
import { StateBadge } from "../document/StateBadge";

type ListState =
  | { status: "loading" }
  /** `refreshing`: a new search is in flight; the previous results stay visible meanwhile. */
  | { status: "ready"; list: WindchillDocumentList; refreshing: boolean }
  | { status: "error"; error: ApiError };

interface WindchillDocumentsCardProps {
  onOpen: (documentId: string) => void;
}

const TH = "px-3 py-2 text-left text-xs font-semibold text-muted first:pl-4 last:pr-4";
const TD = "px-3 py-2.5 align-middle first:pl-4 last:pr-4";

export function WindchillDocumentsCard({ onOpen }: WindchillDocumentsCardProps) {
  const searchId = useId();
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query.trim(), 300);
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [importing, setImporting] = useState<string | null>(null);
  const [importError, setImportError] = useState<{ reference: string; error: ApiError } | null>(
    null,
  );

  useEffect(() => {
    const controller = new AbortController();
    setState((current) =>
      current.status === "ready" ? { ...current, refreshing: true } : { status: "loading" },
    );
    listWindchillDocuments(debouncedQuery, { signal: controller.signal })
      .then((list) => setState({ status: "ready", list, refreshing: false }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) setState({ status: "error", error: toApiError(error) });
      });
    return () => controller.abort();
  }, [debouncedQuery, reloadKey]);

  const open = (reference: string) => {
    if (importing) return;
    setImporting(reference);
    setImportError(null);
    importFromWindchill(reference)
      .then((record) => onOpen(record.id))
      .catch((error: unknown) => {
        setImportError({ reference, error: toApiError(error) });
        setImporting(null);
      });
  };

  const developmentOnly = state.status === "ready" && state.list.provider.developmentOnly;
  const searching =
    (state.status === "ready" && state.refreshing) || query.trim() !== debouncedQuery;

  return (
    <Card>
      <CardHeader
        title="Windchill documents"
        actions={
          developmentOnly ? (
            <Badge
              tone="warning"
              title="Served by the mock Windchill provider. Not connected to Windchill."
            >
              Mock data · Development only
            </Badge>
          ) : null
        }
      />
      <div className="border-b border-line px-4 py-3">
        <label htmlFor={searchId} className="sr-only">
          Search documents
        </label>
        <div className="relative">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted"
          />
          <input
            id={searchId}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by number, name or location"
            autoComplete="off"
            className="h-8 w-full rounded-control border border-line-strong bg-surface pr-9 pl-8 text-sm text-ink placeholder:text-muted hover:border-subtle focus-visible:border-primary"
          />
          {searching && state.status === "ready" ? (
            <Spinner
              label="Searching"
              className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-muted"
            />
          ) : null}
        </div>
      </div>

      {importError ? (
        <div className="border-b border-line px-4 py-3">
          <ErrorState
            compact
            error={importError.error}
            onRetry={() => open(importError.reference)}
          />
        </div>
      ) : null}

      {state.status === "loading" ? (
        <TableSkeleton />
      ) : state.status === "error" ? (
        <div className="p-4">
          <ErrorState error={state.error} onRetry={() => setReloadKey((key) => key + 1)} />
        </div>
      ) : state.list.items.length === 0 ? (
        <EmptyState
          compact
          icon={<FolderOpen />}
          title={
            debouncedQuery
              ? `No documents match “${debouncedQuery}”.`
              : "No documents are available."
          }
        />
      ) : (
        <DocumentResults items={state.list.items} importing={importing} onOpen={open} />
      )}
    </Card>
  );
}

interface DocumentTableProps {
  items: readonly WindchillDocument[];
  importing: string | null;
  onOpen: (reference: string) => void;
}

/** A table from `sm` up; a stacked list on phones, where six columns do not fit. */
function DocumentResults(props: DocumentTableProps) {
  const wide = useMediaQuery("(min-width: 640px)");
  return wide ? <DocumentTable {...props} /> : <DocumentStack {...props} />;
}

function DocumentTable({ items, importing, onOpen }: DocumentTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-surface-muted">
          <tr className="border-b border-line">
            <th scope="col" className={cx(TH, "w-28")}>
              Number
            </th>
            <th scope="col" className={TH}>
              Name
            </th>
            <th scope="col" className={cx(TH, "w-14")}>
              Rev
            </th>
            <th scope="col" className={cx(TH, "w-28")}>
              State
            </th>
            <th scope="col" className={cx(TH, "max-md:hidden")}>
              Location
            </th>
            <th scope="col" className={cx(TH, "w-32 max-md:hidden")}>
              Modified
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.map((item) => {
            const { metadata } = item;
            const busy = importing === item.reference;
            return (
              <tr
                key={item.reference}
                onClick={() => onOpen(item.reference)}
                aria-busy={busy || undefined}
                className={cx(
                  "cursor-pointer transition-colors hover:bg-primary-bg/50",
                  importing && !busy && "opacity-60",
                )}
              >
                <td className={cx(TD, "font-mono text-xs whitespace-nowrap text-ink tabular-nums")}>
                  {metadata.number ?? "—"}
                </td>
                <td className={TD}>
                  <button
                    type="button"
                    disabled={importing !== null}
                    className="flex items-center gap-2 rounded text-left font-medium text-primary hover:text-primary-hover hover:underline disabled:cursor-default disabled:no-underline"
                  >
                    {metadata.name}
                    {busy ? <Spinner label={`Opening ${metadata.name}`} /> : null}
                  </button>
                </td>
                <td className={cx(TD, "font-mono text-xs whitespace-nowrap tabular-nums")}>
                  {formatVersion(metadata) ?? "—"}
                </td>
                <td className={TD}>
                  <StateBadge state={metadata.state} />
                </td>
                <td className={cx(TD, "text-muted max-md:hidden")}>{metadata.location ?? "—"}</td>
                <td className={cx(TD, "whitespace-nowrap text-muted tabular-nums max-md:hidden")}>
                  {metadata.modifiedDate ? (
                    <time dateTime={metadata.modifiedDate}>
                      {formatDate(metadata.modifiedDate)}
                    </time>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DocumentStack({ items, importing, onOpen }: DocumentTableProps) {
  return (
    <ul className="divide-y divide-line">
      {items.map((item) => {
        const { metadata } = item;
        const busy = importing === item.reference;
        const version = formatVersion(metadata);
        return (
          <li key={item.reference}>
            <button
              type="button"
              disabled={importing !== null}
              aria-busy={busy || undefined}
              onClick={() => onOpen(item.reference)}
              className={cx(
                "block w-full px-4 py-3 text-left transition-colors hover:bg-primary-bg/50 disabled:cursor-default",
                importing && !busy && "opacity-60",
              )}
            >
              <span className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink tabular-nums">
                  {metadata.number ?? "—"}
                </span>
                {version ? (
                  <span className="font-mono text-xs text-muted tabular-nums">{version}</span>
                ) : null}
                <StateBadge state={metadata.state} />
                {busy ? <Spinner label={`Opening ${metadata.name}`} className="ml-auto" /> : null}
              </span>
              <span className="mt-1 block font-medium text-primary">{metadata.name}</span>
              {metadata.location ? (
                <span className="mt-0.5 block truncate text-xs text-muted">
                  {metadata.location}
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function TableSkeleton() {
  return (
    <div aria-busy="true" className="divide-y divide-line">
      <p role="status" className="sr-only">
        Loading documents
      </p>
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="flex items-center gap-4 px-4 py-3">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 flex-1" />
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}
