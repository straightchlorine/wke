import type { ReactNode } from "react";
import type { Budget } from "../lib/budget";
import { budgetAlias } from "../lib/budget";

const LINK_BUTTON =
  "text-accent underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink [@media(pointer:coarse)]:min-h-11";

export interface CutRowProps {
  /** The section's label, read by screen readers after the button text. */
  label: string;
  /** How many chunk ids the current budget held back inside this section. */
  heldBackCount: number;
  /** The next larger budget, which would show them. */
  nextBudget: Budget;
  onShowAtBudget: (budget: Budget) => void;
  className?: string;
}

/** A line under a section that says how many of its passages the current budget left out, with a button to show them at the next budget. */
export function CutRow({
  label,
  heldBackCount,
  nextBudget,
  onShowAtBudget,
  className = "",
}: CutRowProps) {
  if (heldBackCount <= 0) {
    return null;
  }
  return (
    <div
      className={`flex flex-wrap items-baseline gap-x-2 border-t-(length:--hairline) border-dashed border-rule py-2 text-13 text-ink-3 ${className}`}
    >
      <span>
        {heldBackCount} {heldBackCount === 1 ? "passage" : "passages"} left out at this budget.
      </span>
      <button
        type="button"
        data-budget={budgetAlias(nextBudget)}
        onClick={() => onShowAtBudget(nextBudget)}
        className={LINK_BUTTON}
      >
        Show at {budgetAlias(nextBudget)}
        <span className="sr-only">: {label}</span>
      </button>
    </div>
  );
}

export interface FoldRowProps {
  label: string;
  /** Why the section is not shown, e.g. "Left out entirely at this budget." */
  reason: ReactNode;
  /** Omit together with `onShowAtBudget` when the current budget is already the largest. */
  nextBudget?: Budget;
  onShowAtBudget?: (budget: Budget) => void;
  /** Toggles an in-place read of the section without changing the export. */
  onReadHere: () => void;
  expanded: boolean;
  className?: string;
}

/** A line in place of a section the current budget left out entirely, with buttons to show it at the next budget or read it in place. */
export function FoldRow({
  label,
  reason,
  nextBudget,
  onShowAtBudget,
  onReadHere,
  expanded,
  className = "",
}: FoldRowProps) {
  return (
    <div
      className={`border-t-(length:--hairline) border-dashed border-rule py-3 text-13 text-ink-3 ${className}`}
    >
      <p>
        <span className="font-medium text-ink-2">{label}</span>: not shown. {reason}
      </p>
      <div className="mt-1 flex flex-wrap gap-x-4">
        {nextBudget != null && onShowAtBudget ? (
          <button
            type="button"
            data-budget={budgetAlias(nextBudget)}
            onClick={() => onShowAtBudget(nextBudget)}
            className={LINK_BUTTON}
          >
            Show at {budgetAlias(nextBudget)}
            <span className="sr-only">: {label}</span>
          </button>
        ) : null}
        <button type="button" aria-expanded={expanded} onClick={onReadHere} className={LINK_BUTTON}>
          {expanded ? "Hide" : "Read here without changing the export"}
          <span className="sr-only">: {label}</span>
        </button>
      </div>
    </div>
  );
}
