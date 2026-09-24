import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";

import { isAbortError, listDocuments, toApiError, type ApiError } from "../../api/client";
import type { DocumentRecord } from "../../api/types";
import { ErrorState } from "../../components/ErrorState";
import { Card, CardHeader } from "../../components/ui/Card";
import { formatDateTime, formatRelativeTime, formatVersion } from "../../lib/format";
import { StateBadge } from "../document/StateBadge";

type State =
  | { status: "loading" }
  | { status: "ready"; items: DocumentRecord[] }
  | { status: "error"; error: ApiError };

interface RecentDocumentsProps {
  onOpen: (documentId: string) => void;
}

/** Documents already registered with the service (shown only when there are any). */
export function RecentDocuments({ onOpen }: RecentDocumentsProps) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listDocuments({ signal: controller.signal })
      .then((list) => setState({ status: "ready", items: list.items }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) setState({ status: "error", error: toApiError(error) });
      });
    return () => controller.abort();
  }, [reloadKey]);

  if (state.status === "loading") return null;
  if (state.status === "error") {
    return (
      <Card>
        <CardHeader title="Recent documents" />
        <div className="p-4">
          <ErrorState compact error={state.error} onRetry={() => setReloadKey((key) => key + 1)} />
        </div>
      </Card>
    );
  }
  if (state.items.length === 0) return null;

  return (
    <Card>
      <CardHeader title="Recent documents" />
      <ul className="divide-y divide-line">
        {state.items.map((record) => {
          const { metadata } = record;
          const version = formatVersion(metadata);
          return (
            <li key={record.id}>
              <button
                type="button"
                onClick={() => onOpen(record.id)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-primary-bg/50"
              >
                <span className="w-24 shrink-0 truncate font-mono text-xs text-ink tabular-nums max-sm:hidden">
                  {metadata.number ?? "—"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-primary">{metadata.name}</span>
                  <span className="block truncate text-xs text-muted">
                    {[
                      metadata.number,
                      version ? `Rev ${version}` : null,
                      record.source === "upload" ? "Uploaded file" : "Windchill",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                {metadata.state ? (
                  <StateBadge state={metadata.state} className="max-sm:hidden" />
                ) : null}
                <time
                  dateTime={record.createdAt}
                  title={formatDateTime(record.createdAt)}
                  className="shrink-0 text-xs text-muted tabular-nums max-md:hidden"
                >
                  {formatRelativeTime(record.createdAt)}
                </time>
                <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-subtle" />
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
