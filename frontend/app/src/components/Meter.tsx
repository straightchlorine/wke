import type { ReactNode } from "react";

export interface MeterProps {
  /** The visible label, for example "6 of 8 sections at 8k". */
  label: string;
  /** Fraction filled, 0 to 1. */
  fraction: number;
  /** Content after the label, for example an InfoDot with detail the label leaves out to stay on one line. */
  info?: ReactNode;
  className?: string;
}

/**
 * A label over a thin filled track.
 * The native `<meter>` carries the value for assistive technology. The visible track is aria-hidden so platform meter styling cannot change its height.
 */
export function Meter({ label, fraction, info, className = "" }: MeterProps) {
  const clamped = Math.min(1, Math.max(0, fraction));
  return (
    <div className={className}>
      <div className="mb-1 flex items-baseline text-12 text-ink-2 tabular-nums">
        <span className="min-w-0 truncate">{label}</span>
        {info}
      </div>
      <meter className="sr-only" min={0} max={1} value={clamped} aria-label={label} />
      <div aria-hidden="true" className="h-1 w-full bg-sunken">
        <div
          className="h-full bg-accent transition-[width] duration-(--motion-base) ease-(--ease-out) motion-reduce:transition-none"
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
    </div>
  );
}
