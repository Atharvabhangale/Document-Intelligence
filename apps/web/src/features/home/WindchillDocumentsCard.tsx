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
import { cx } from "../../lib/cx";
import { formatDate, formatVersion } from "../../lib/format";
import { StateBadge } from "../document/StateBadge";

type ListState =
  | { status: "loading" }
  | { status: "ready"; list: WindchillDocumentList }
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
    setState({ status: "loading" });
    listWindchillDocuments(debouncedQuery, { signal: controller.signal })
      .then((list) => setState({ status: "ready", list }))
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
            placeholder="Search by number or name"
            autoComplete="off"
            className="h-8 w-full rounded-control border border-line-strong bg-surface pr-3 pl-8 text-sm text-ink placeholder:text-muted hover:border-subtle focus-visible:border-primary"
          />
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
        <DocumentTable items={state.list.items} importing={importing} onOpen={open} />
      )}
    </Card>
  );
}

interface DocumentTableProps {
  items: readonly WindchillDocument[];
  importing: string | null;
  onOpen: (reference: string) => void;
}

function DocumentTable({ items, importing, onOpen }: DocumentTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-surface-muted">
          <tr className="border-b border-line">
            <th scope="col" className={TH}>
              Number
            </th>
            <th scope="col" className={TH}>
              Name
            </th>
            <th scope="col" className={TH}>
              Rev
            </th>
            <th scope="col" className={TH}>
              State
            </th>
            <th scope="col" className={cx(TH, "max-md:hidden")}>
              Location
            </th>
            <th scope="col" className={cx(TH, "max-md:hidden")}>
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
