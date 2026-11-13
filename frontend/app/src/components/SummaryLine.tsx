export interface SummaryLineProps {
  /** Why the section has no summary. */
  detail: string;
  className?: string;
}

/**
 * Shown in a ModelPanel's place when a section has no summary.
 * It shows only the `detail` text, with no stand-in sentences, model name or chip.
 */
export function SummaryLine({ detail, className = "" }: SummaryLineProps) {
  return (
    <p role="note" className={`border-l-2 border-rule-strong pl-3 text-12 text-ink-3 ${className}`}>
      {detail}
    </p>
  );
}
