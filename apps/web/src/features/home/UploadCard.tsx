import { FileUp, Info } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";

import { toApiError, uploadDocument, type ApiError } from "../../api/client";
import { ErrorState } from "../../components/ErrorState";
import { Button } from "../../components/ui/Button";
import { Card, CardHeader } from "../../components/ui/Card";
import { Notice } from "../../components/ui/Notice";
import { Spinner } from "../../components/ui/Spinner";
import { cx } from "../../lib/cx";
import { formatBytes } from "../../lib/format";

const DEFAULT_MAX_UPLOAD_MB = 25;

/** Client-side checks before upload (the backend validates again). */
export function validatePdf(file: File, maxUploadMb: number): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return `“${file.name}” is not a PDF. Only PDF documents are supported.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  if (file.size > maxUploadMb * 1024 * 1024) {
    return `“${file.name}” is ${formatBytes(file.size)}. The maximum size is ${maxUploadMb} MB.`;
  }
  return null;
}

interface UploadCardProps {
  maxUploadMb: number | undefined;
  onUploaded: (documentId: string) => void;
}

export function UploadCard({ maxUploadMb = DEFAULT_MAX_UPLOAD_MB, onUploaded }: UploadCardProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const lastFile = useRef<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const upload = (file: File) => {
    lastFile.current = file;
    setError(null);
    const problem = validatePdf(file, maxUploadMb);
    setValidationError(problem);
    if (problem) return;
    setUploading(file.name);
    uploadDocument(file)
      .then((record) => onUploaded(record.id))
      .catch((caught: unknown) => {
        setError(toApiError(caught));
        setUploading(null);
      });
  };

  const onFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    if (files.length > 1) {
      setValidationError("Drop a single PDF file.");
      return;
    }
    upload(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    if (uploading) return;
    onFiles(event.dataTransfer.files);
  };

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!uploading) setDragActive(true);
  };

  return (
    <Card>
      <CardHeader title="Upload a PDF" description={`PDF only · up to ${maxUploadMb} MB`} />
      <div className="space-y-3 p-4">
        <div
          onDragEnter={onDragOver}
          onDragOver={onDragOver}
          onDragLeave={() => setDragActive(false)}
          onDrop={onDrop}
          className={cx(
            "flex flex-col items-center gap-2 rounded-card border border-dashed px-4 py-6 text-center transition-colors",
            dragActive ? "border-primary bg-primary-bg" : "border-line-strong bg-surface-muted",
          )}
        >
          {uploading ? (
            <div role="status" className="flex flex-col items-center gap-2">
              <Spinner className="text-primary" />
              <p className="font-medium text-ink">Uploading and extracting text…</p>
              <p className="max-w-full truncate text-xs text-muted">{uploading}</p>
            </div>
          ) : (
            <>
              <FileUp aria-hidden="true" className="size-6 text-muted" />
              <p className="text-ink">
                <span className="font-medium">Drag and drop a PDF here</span>
                <span className="text-muted"> or</span>
              </p>
              <Button size="sm" onClick={() => inputRef.current?.click()}>
                Browse files
              </Button>
              <label htmlFor={inputId} className="sr-only">
                Choose a PDF file to upload
              </label>
              <input
                ref={inputRef}
                id={inputId}
                type="file"
                accept=".pdf,application/pdf"
                className="sr-only"
                tabIndex={-1}
                onChange={(event) => {
                  onFiles(event.target.files);
                  event.target.value = "";
                }}
              />
            </>
          )}
        </div>

        {validationError ? (
          <Notice tone="danger" role="alert">
            {validationError}
          </Notice>
        ) : null}
        {error ? (
          <ErrorState
            compact
            error={error}
            onRetry={() => {
              if (lastFile.current) upload(lastFile.current);
            }}
          />
        ) : null}

        <p className="flex gap-1.5 text-xs text-muted">
          <Info aria-hidden="true" className="mt-px size-3.5 shrink-0" />
          Uploads are for development testing. Uploaded files are stored on the development server
          and are not connected to Windchill.
        </p>
      </div>
    </Card>
  );
}
