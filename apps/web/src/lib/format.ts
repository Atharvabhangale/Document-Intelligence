/** Display formatting helpers (locale-aware, never throw on unexpected input). */
import type { DocumentMetadata } from "../api/types";

/** Windchill-style version label: "A.3", "A" or null. */
export function formatVersion(
  metadata: Pick<DocumentMetadata, "revision" | "iteration">,
): string | null {
  const { revision, iteration } = metadata;
  if (revision && iteration) return `${revision}.${iteration}`;
  return revision || null;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"] as const;
  let value = bytes / 1024;
  let unit: (typeof units)[number] = "KB";
  for (const next of units.slice(1)) {
    if (value < 1024) break;
    value /= 1024;
    unit = next;
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 1 : 0 })} ${unit}`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString();
}

function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Localized date and time, e.g. "Mar 14, 2026, 10:30 AM". */
export function formatDateTime(iso: string | null | undefined): string {
  const date = parseDate(iso);
  if (!date) return iso ?? "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    date,
  );
}

/** Localized date only, e.g. "Mar 14, 2026". */
export function formatDate(iso: string | null | undefined): string {
  const date = parseDate(iso);
  if (!date) return iso ?? "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

const RELATIVE_STEPS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.345],
  ["month", 12],
  ["year", Number.POSITIVE_INFINITY],
];

/** Relative time such as "5 minutes ago" or "just now". */
export function formatRelativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  const date = parseDate(iso);
  if (!date) return "—";
  let delta = (date.getTime() - now.getTime()) / 1000;
  if (Math.abs(delta) < 45) return "just now";
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(delta) < size) return rtf.format(Math.round(delta), unit);
    delta /= size;
  }
  return formatDateTime(iso);
}

/** Durations such as "850 ms", "12.4 s" or "1 min 05 s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} min ${String(rest).padStart(2, "0")} s`;
}

/** Elapsed timer "m:ss". */
export function formatElapsed(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** "3", "3 and 7", "3, 5 and 7". */
export function formatList(items: readonly (string | number)[]): string {
  const parts = items.map(String);
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return count === 1 ? singular : plural;
}

const PROVIDER_LABELS: Readonly<Record<string, string>> = {
  anthropic: "Anthropic",
  ollama: "Ollama",
  fake: "Simulated",
};

/** Human label of an AI provider id ("anthropic" -> "Anthropic"). */
export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1);
}
