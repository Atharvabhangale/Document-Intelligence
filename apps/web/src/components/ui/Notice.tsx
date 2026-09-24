import { CircleAlert, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "../../lib/cx";

export type NoticeTone = "warning" | "info" | "danger" | "neutral";

const TONES: Record<NoticeTone, { box: string; icon: string; Icon: typeof Info }> = {
  warning: { box: "border-warning-line bg-warning-bg", icon: "text-warning", Icon: TriangleAlert },
  info: { box: "border-info/25 bg-info-bg", icon: "text-info", Icon: Info },
  danger: { box: "border-danger/25 bg-danger-bg", icon: "text-danger", Icon: CircleAlert },
  neutral: { box: "border-line bg-surface-muted", icon: "text-muted", Icon: Info },
};

interface NoticeProps {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  /** `alert` for errors that appear in response to an action; default is a static note. */
  role?: "alert" | "status" | "note";
  className?: string;
}

/** Inline notice (warnings, caveats, information). Always icon + text, never color alone. */
export function Notice({ tone = "info", title, children, role = "note", className }: NoticeProps) {
  const { box, icon, Icon } = TONES[tone];
  return (
    <div
      role={role}
      className={cx(
        "flex gap-2.5 rounded-control border px-3 py-2.5 text-sm text-ink",
        box,
        className,
      )}
    >
      <Icon aria-hidden="true" className={cx("mt-0.5 size-4 shrink-0", icon)} />
      <div className="min-w-0 space-y-0.5">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className="text-ink/90">{children}</div> : null}
      </div>
    </div>
  );
}
