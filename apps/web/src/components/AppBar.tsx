import { Cpu, ScanText, TriangleAlert } from "lucide-react";

import type { HealthResponse } from "../api/types";
import { cx } from "../lib/cx";
import { providerLabel } from "../lib/format";

interface AppBarProps {
  health: HealthResponse | null;
  healthFailed: boolean;
  onHome: () => void;
}

export function AppBar({ health, healthFailed, onHome }: AppBarProps) {
  return (
    <header className="on-dark bg-appbar text-white">
      <div className="mx-auto flex h-12 max-w-[1600px] items-center justify-between gap-3 px-4">
        <a
          href="/"
          onClick={(event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
            event.preventDefault();
            onHome();
          }}
          className="flex shrink-0 items-center gap-2 rounded-control"
        >
          <ScanText aria-hidden="true" className="size-5 shrink-0 text-white" />
          <span className="text-[15px] font-semibold tracking-tight whitespace-nowrap">
            Document Intelligence
          </span>
          <span className="hidden text-sm whitespace-nowrap text-appbar-muted sm:inline">
            for Windchill
          </span>
        </a>
        <ModelPill health={health} failed={healthFailed} />
      </div>
    </header>
  );
}

function ModelPill({ health, failed }: { health: HealthResponse | null; failed: boolean }) {
  if (failed) {
    return (
      <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-danger/25 px-2.5 text-xs font-medium text-white">
        <TriangleAlert aria-hidden="true" className="size-3.5" />
        Service unavailable
      </span>
    );
  }
  if (!health) {
    return (
      <span
        aria-hidden="true"
        className="h-6 w-48 rounded-full bg-white/10 motion-safe:animate-pulse"
      />
    );
  }
  const { ai } = health;
  const configured = ai.configured;
  const label = `${ai.model} · ${providerLabel(ai.provider)}`;
  return (
    <span
      title={
        configured
          ? `AI model: ${ai.model} (${providerLabel(ai.provider)})`
          : "The AI provider is not configured on the server."
      }
      className={cx(
        "inline-flex h-6 min-w-0 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium",
        configured ? "bg-white/10 text-white" : "bg-warning-bg text-warning",
      )}
    >
      {configured ? (
        <Cpu aria-hidden="true" className="size-3.5 shrink-0 text-appbar-muted" />
      ) : (
        <TriangleAlert aria-hidden="true" className="size-3.5 shrink-0" />
      )}
      <span className="sr-only">AI model: </span>
      <span className="truncate font-mono tabular-nums">{label}</span>
      {configured ? null : <span className="whitespace-nowrap">· not configured</span>}
    </span>
  );
}
