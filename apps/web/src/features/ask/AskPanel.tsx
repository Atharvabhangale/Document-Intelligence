import { CircleQuestionMark, MessageSquareText, SendHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ask, isAbortError, toApiError, type ApiError } from "../../api/client";
import type { AskResponse, Citation } from "../../api/types";
import { ErrorState } from "../../components/ErrorState";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { formatDuration } from "../../lib/format";
import { CitationChips } from "../report/CitationChip";
import { ASK_SECTION_ID } from "../report/ReportView";

export const SOP_SUGGESTIONS = [
  "What PPE is required?",
  "What are the key inspection criteria?",
  "Which steps are safety-critical?",
] as const;

const DEFAULT_MAX_CHARS = 1000;

type Entry =
  | { id: number; question: string; status: "pending" }
  | { id: number; question: string; status: "done"; response: AskResponse }
  | { id: number; question: string; status: "error"; error: ApiError };

interface AskPanelProps {
  documentId: string;
  /** Document type (suggested questions are shown for SOPs). */
  documentType?: string | null;
  maxQuestionChars?: number;
  /** False when the AI provider is not configured (asking is then disabled). */
  aiAvailable?: boolean;
  onOpenCitation: (citation: Citation) => void;
}

/**
 * "Ask this Document": grounded Q&A over the open document. History is shown newest first,
 * directly below the question box.
 */
export function AskPanel({
  documentId,
  documentType,
  maxQuestionChars = DEFAULT_MAX_CHARS,
  aiAvailable = true,
  onOpenCitation,
}: AskPanelProps) {
  const inputId = useId();
  const counterId = useId();
  const [question, setQuestion] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const nextId = useRef(1);
  const controllers = useRef(new Set<AbortController>());

  useEffect(() => {
    const active = controllers.current;
    return () => {
      for (const controller of active) controller.abort();
      active.clear();
    };
  }, []);

  const pending = entries.some((entry) => entry.status === "pending");
  const trimmed = question.trim();
  const canSubmit =
    aiAvailable && trimmed.length > 0 && trimmed.length <= maxQuestionChars && !pending;
  const suggestions = documentType?.trim().toUpperCase() === "SOP" ? SOP_SUGGESTIONS : [];

  const run = (id: number, text: string) => {
    const controller = new AbortController();
    controllers.current.add(controller);
    ask(documentId, text, { signal: controller.signal })
      .then((response) => {
        setEntries((list) =>
          list.map((entry) =>
            entry.id === id ? { id, question: text, status: "done", response } : entry,
          ),
        );
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        setEntries((list) =>
          list.map((entry) =>
            entry.id === id
              ? { id, question: text, status: "error", error: toApiError(error) }
              : entry,
          ),
        );
      })
      .finally(() => controllers.current.delete(controller));
  };

  const submit = (text: string) => {
    const value = text.trim();
    if (!aiAvailable || !value || value.length > maxQuestionChars || pending) return;
    const id = nextId.current++;
    setEntries((list) => [{ id, question: value, status: "pending" }, ...list]);
    setQuestion("");
    run(id, value);
  };

  const retry = (entry: Entry) => {
    setEntries((list) =>
      list.map((item) =>
        item.id === entry.id ? { id: entry.id, question: entry.question, status: "pending" } : item,
      ),
    );
    run(entry.id, entry.question);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(question);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit(question);
    }
  };

  // Fallback for browsers without `field-sizing: content` (1–3 rows).
  const rows = Math.min(3, Math.max(1, question.split("\n").length));

  return (
    <Card>
      <section id={ASK_SECTION_ID} aria-labelledby={`${inputId}-title`} className="scroll-mt-16">
        <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <MessageSquareText aria-hidden="true" className="size-4 text-muted" />
          <h2 id={`${inputId}-title`} tabIndex={-1} className="text-[15px] font-semibold text-ink">
            Ask this Document
          </h2>
        </div>
        <div className="space-y-3 px-4 py-4">
          <form onSubmit={onSubmit} className="space-y-2">
            <label htmlFor={inputId} className="sr-only">
              Question about this document
            </label>
            <div className="flex items-end gap-2">
              <textarea
                id={inputId}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={onKeyDown}
                rows={rows}
                maxLength={maxQuestionChars}
                disabled={!aiAvailable}
                aria-describedby={counterId}
                placeholder="Ask a question about this document…"
                className="max-h-[4.75rem] min-h-8 flex-1 resize-none rounded-control [field-sizing:content] border border-line-strong bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-muted hover:border-subtle focus-visible:border-primary disabled:bg-surface-muted"
              />
              <Button
                type="submit"
                variant="primary"
                icon={<SendHorizontal />}
                disabled={!canSubmit}
              >
                Ask
              </Button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <span>
                {aiAvailable
                  ? "Answers are based only on this document. Enter to ask, Shift+Enter for a new line."
                  : "Asking is unavailable: the AI provider is not configured."}
              </span>
              <span id={counterId} className="tabular-nums">
                <span className="sr-only">Characters used: </span>
                {question.length} / {maxQuestionChars}
              </span>
            </div>
          </form>

          {suggestions.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted">Suggested:</span>
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  disabled={!aiAvailable || pending}
                  onClick={() => submit(suggestion)}
                  className="h-7 rounded-full border border-line-strong bg-surface px-2.5 text-xs text-ink hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-55"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}

          {entries.length > 0 ? (
            <ol aria-label="Questions and answers" className="space-y-3">
              {entries.map((entry) => (
                <li key={entry.id}>
                  <AskEntry
                    entry={entry}
                    onRetry={() => retry(entry)}
                    onOpenCitation={onOpenCitation}
                  />
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      </section>
    </Card>
  );
}

interface AskEntryProps {
  entry: Entry;
  onRetry: () => void;
  onOpenCitation: (citation: Citation) => void;
}

function AskEntry({ entry, onRetry, onOpenCitation }: AskEntryProps) {
  return (
    <article className="rounded-card border border-line">
      <p className="border-b border-line bg-surface-muted px-3 py-2 font-semibold break-words text-ink">
        {entry.question}
      </p>
      <div className="px-3 py-2.5">
        {entry.status === "pending" ? (
          <p role="status" className="flex items-center gap-2 text-muted">
            <Spinner />
            Searching the document for an answer…
          </p>
        ) : entry.status === "error" ? (
          <ErrorState compact error={entry.error} onRetry={onRetry} />
        ) : (
          <Answer response={entry.response} onOpenCitation={onOpenCitation} />
        )}
      </div>
    </article>
  );
}

function Answer({
  response,
  onOpenCitation,
}: {
  response: AskResponse;
  onOpenCitation: (c: Citation) => void;
}) {
  const meta = `${response.provenance.model} · ${formatDuration(response.provenance.durationMs)}`;
  if (!response.answerable) {
    return (
      <div className="space-y-1.5">
        <p className="flex items-center gap-1.5 font-medium text-ink">
          <CircleQuestionMark aria-hidden="true" className="size-4 text-muted" />
          Not found in this document
        </p>
        <p className="whitespace-pre-line text-muted">{response.answer}</p>
        <p className="text-xs text-muted">{meta}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="whitespace-pre-line text-ink">{response.answer}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CitationChips citations={response.citations} onOpen={onOpenCitation} />
        <span className="text-xs text-muted">AI-generated · {meta}</span>
      </div>
    </div>
  );
}
