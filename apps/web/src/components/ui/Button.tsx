import type { ComponentProps, ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md";

const BASE =
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-control font-medium " +
  "whitespace-nowrap transition-colors select-none disabled:cursor-not-allowed disabled:opacity-55";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary text-white shadow-card hover:bg-primary-hover disabled:hover:bg-primary",
  secondary:
    "border border-line-strong bg-surface text-ink hover:bg-surface-muted hover:border-subtle " +
    "disabled:hover:bg-surface",
  ghost: "text-muted hover:bg-neutral-bg hover:text-ink disabled:hover:bg-transparent",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-2 text-xs [&_svg]:size-3.5",
  md: "h-8 px-3 text-sm [&_svg]:size-4",
};

export function buttonClasses(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cx(BASE, VARIANTS[variant], SIZES[size], className);
}

interface ButtonProps extends ComponentProps<"button"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Leading icon (rendered aria-hidden). */
  icon?: ReactNode;
  /** Shows a spinner in place of the icon and disables the button. */
  loading?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  loading = false,
  disabled,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <Spinner />
      ) : icon ? (
        <span aria-hidden="true" className="contents">
          {icon}
        </span>
      ) : null}
      {children}
    </button>
  );
}

interface ButtonLinkProps extends ComponentProps<"a"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
}

/** An anchor styled as a button (for links to our own API, e.g. "Open PDF"). */
export function ButtonLink({
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <a className={buttonClasses(variant, size, className)} {...rest}>
      {icon ? (
        <span aria-hidden="true" className="contents">
          {icon}
        </span>
      ) : null}
      {children}
    </a>
  );
}

interface IconButtonProps extends ComponentProps<"button"> {
  /** Accessible name (also shown as a tooltip). */
  label: string;
  size?: ButtonSize;
  children: ReactNode;
}

/** Square icon-only button with an accessible label. */
export function IconButton({
  label,
  size = "md",
  className,
  children,
  type = "button",
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        BASE,
        VARIANTS.ghost,
        size === "sm" ? "size-7 [&_svg]:size-4" : "size-8 [&_svg]:size-4",
        className,
      )}
      {...rest}
    >
      <span aria-hidden="true" className="contents">
        {children}
      </span>
    </button>
  );
}
