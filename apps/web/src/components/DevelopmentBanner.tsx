import { FlaskConical } from "lucide-react";

interface DevelopmentBannerProps {
  /** Mock Windchill data (provider or open document is development-only). */
  mockWindchill: boolean;
  /** The AI provider is the development fake. */
  simulatedAi: boolean;
}

/**
 * Persistent development banner. It has no dismiss control on purpose: users must always be
 * able to tell that the data or the AI output is not real.
 */
export function DevelopmentBanner({ mockWindchill, simulatedAi }: DevelopmentBannerProps) {
  if (!mockWindchill && !simulatedAi) return null;
  const messages = [
    mockWindchill ? "Mock Windchill data. Not connected to Windchill." : null,
    simulatedAi ? "AI output is simulated (fake provider)." : null,
  ].filter((message): message is string => message !== null);
  return (
    <div
      role="note"
      aria-label="Development environment"
      className="border-b border-warning-line bg-warning-bg text-warning"
    >
      <div className="mx-auto flex min-h-8 max-w-[1600px] items-center gap-2 px-4 py-1 text-xs font-medium">
        <FlaskConical aria-hidden="true" className="size-3.5 shrink-0" />
        <p>
          <strong className="font-semibold tracking-wide">DEVELOPMENT ONLY</strong>
          {" — "}
          {messages.join(" ")}
        </p>
      </div>
    </div>
  );
}
