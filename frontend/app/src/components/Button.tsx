import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "small" | "quiet";

export interface ButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "disabled" | "className"
> {
  children: ReactNode;
  variant?: ButtonVariant;
  /** True while the button waits on a request. It sets aria-disabled instead of disabled, so the button stays focusable and announced, and clicks are ignored. */
  waiting?: boolean;
  className?: string;
}

// Primary, secondary and quiet take their height from --control-h, which grows
// under a coarse pointer. Small is shorter and adds an invisible larger hit
// area under a coarse pointer. Quiet has no background and inherits its text
// colour, so it fits a header row that sets its own.
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-on-accent font-semibold text-14 h-(--control-h) px-4 hover:bg-accent-ink",
  secondary:
    "bg-sheet text-ink border-(length:--hairline) border-rule-strong text-14 h-(--control-h) px-4 hover:bg-wash",
  small:
    "relative bg-sheet text-ink border-(length:--hairline) border-rule-strong text-13 h-6 px-2 hover:bg-wash " +
    "pointer-coarse:before:absolute pointer-coarse:before:left-1/2 pointer-coarse:before:top-1/2 " +
    "pointer-coarse:before:h-11 pointer-coarse:before:w-[max(100%,44px)] " +
    "pointer-coarse:before:-translate-1/2 pointer-coarse:before:content-['']",
  quiet:
    "border-none bg-transparent text-inherit text-12 h-(--control-h) px-3 underline-offset-4 " +
    "hover:text-ink hover:underline",
};

/** Returns the classes `Button` applies for a variant, for use on a non-button element such as a router `Link`. */
export function buttonClasses(variant: ButtonVariant = "secondary"): string {
  return `inline-flex items-center justify-center rounded-2 transition-colors duration-(--motion-fast) ${VARIANT_CLASSES[variant]}`;
}

/** A button that stays focusable but ignores clicks while `waiting`. */
export function Button({
  children,
  variant = "secondary",
  waiting = false,
  className = "",
  onClick,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      aria-disabled={waiting || undefined}
      onClick={(event) => {
        if (waiting) {
          return;
        }
        onClick?.(event);
      }}
      className={`${buttonClasses(variant)} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
