import type { ReactNode } from "react";

export interface SectionTitleProps {
  children: ReactNode;
  /** A count shown after the title. */
  count?: ReactNode;
  level?: 2 | 3;
  /** An explanatory line shown below the heading. */
  sub?: ReactNode;
  className?: string;
}

/** A section heading with an optional count and explanatory line. */
export function SectionTitle({
  children,
  count,
  level = 2,
  sub,
  className = "",
}: SectionTitleProps) {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <div className={className}>
      <div className="flex items-baseline gap-x-2">
        <Heading className="font-serif text-16 italic text-ink">{children}</Heading>
        {count != null ? <span className="font-sans text-13 text-ink-3">{count}</span> : null}
      </div>
      {sub != null ? <p className="mt-1 text-13 text-ink-2">{sub}</p> : null}
    </div>
  );
}
