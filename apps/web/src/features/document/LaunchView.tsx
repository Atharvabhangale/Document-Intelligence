import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";

import { importFromWindchill, isAbortError, toApiError, type ApiError } from "../../api/client";
import { ErrorState } from "../../components/ErrorState";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";

interface LaunchViewProps {
  /** Opaque Windchill object reference from the launching action. */
  reference: string;
  onOpened: (documentId: string) => void;
  onHome: () => void;
}

/**
 * Entry point of a (simulated) Windchill "AI Summarize" action: imports the referenced
 * document through the configured provider, then hands over to the document workspace.
 */
export function LaunchView({ reference, onOpened, onHome }: LaunchViewProps) {
  const [error, setError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    importFromWindchill(reference, { signal: controller.signal })
      .then((record) => onOpened(record.id))
      .catch((caught: unknown) => {
        if (!isAbortError(caught)) setError(toApiError(caught));
      });
    return () => controller.abort();
  }, [reference, attempt, onOpened]);

  return (
    <div className="mx-auto max-w-2xl py-6">
      {error ? (
        <ErrorState
          error={error}
          onRetry={() => setAttempt((value) => value + 1)}
          actions={
            <Button size="sm" icon={<ArrowLeft />} onClick={onHome}>
              All documents
            </Button>
          }
        />
      ) : (
        <Card className="flex items-start gap-3 px-5 py-5">
          <Spinner className="mt-0.5 text-primary" />
          <div className="min-w-0" role="status">
            <p className="font-semibold text-ink">Opening document from Windchill…</p>
            <p className="mt-1 text-sm text-muted">
              Retrieving the document and extracting its text.
            </p>
            <p className="mt-2 font-mono text-xs break-all text-muted">{reference}</p>
          </div>
        </Card>
      )}
    </div>
  );
}
