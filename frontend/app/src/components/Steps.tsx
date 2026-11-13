export type StepState = "done" | "running" | "waiting";

export interface Step {
  /** The stage's label, for example "Fetching revision". */
  label: string;
  state: StepState;
  /** The stage's own elapsed time, already formatted for display. */
  time?: string;
}

export interface StepsProps {
  steps: Step[];
  className?: string;
}

const MARK_CLASSES: Record<StepState, string> = {
  done: "bg-ink border-ink",
  running: "bg-transparent border-accent animate-spin motion-reduce:animate-none",
  waiting: "bg-transparent border-rule",
};

/**
 * Lists build stages as rows of a mark, a label, a dotted leader and a right-aligned time.
 * All rows share one grid, so every leader ends at the same x.
 */
export function Steps({ steps, className = "" }: StepsProps) {
  return (
    <ol
      className={`grid grid-cols-[auto_auto_1fr_max-content] gap-x-2 border-t-(length:--hairline) border-ink ${className}`}
    >
      {steps.map((step, index) => (
        <li
          key={index}
          className="col-span-full grid grid-cols-subgrid items-baseline py-1 text-13"
        >
          <span
            aria-hidden="true"
            className={`size-2 shrink-0 self-center rounded-full border-(length:--hairline) ${MARK_CLASSES[step.state]}`}
          />
          <span className={step.state === "waiting" ? "text-ink-3" : "text-ink"}>{step.label}</span>
          <span
            aria-hidden="true"
            className="min-w-3 border-b-(length:--hairline) border-dotted border-rule-strong"
          />
          <span className="text-right text-12 tabular-nums text-ink-3">{step.time ?? ""}</span>
        </li>
      ))}
    </ol>
  );
}
