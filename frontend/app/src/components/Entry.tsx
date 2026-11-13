import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { formatNumber } from "../lib/format";
import type { Budget } from "../lib/budget";

export interface EntryProps {
  title: string;
  /** The dossier route's slug, e.g. "Alan_Turing". */
  slug: string;
  /** The selected token budget, carried through as `?budget=`. */
  budget: Budget;
  views: number;
  /** The line under the title, e.g. "4 edits". */
  meta?: ReactNode;
  /** The chip in its own column between the title and the views: a budget badge or a build-state chip. */
  chip?: ReactNode;
  /** Width of the views column in ch, so every row's figure aligns and the title takes the rest. */
  viewsCh?: number;
  /** True when the chip column holds a word ("Building") and not only a budget badge ("32k"). */
  chipWide?: boolean;
  /** True for a topic with a recent live edit: the title is drawn in the stamp colour at medium weight. */
  fresh?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
  /** Exposes the row's link so the page can move focus to it, for example to the first row that "Show all" reveals. */
  linkRef?: (el: HTMLAnchorElement | null) => void;
  className?: string;
}

/** One row of the topic index: the title with an optional meta line, a chip column and the view count, all in one link target. */
export function Entry({
  title,
  slug,
  budget,
  views,
  meta,
  chip,
  viewsCh = 7,
  chipWide = false,
  fresh = false,
  onMouseEnter,
  onMouseLeave,
  onFocus,
  onBlur,
  linkRef,
  className = "",
}: EntryProps) {
  return (
    <li
      className={`flex min-h-12 items-center gap-x-2 border-b-(length:--hairline) border-rule py-1 md:h-12 ${className}`}
    >
      <Link
        ref={linkRef}
        to="/t/$slug"
        params={{ slug }}
        search={{ budget }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        onFocus={onFocus}
        onBlur={onBlur}
        title={title}
        className="hit-coarse min-w-0 flex-1"
      >
        <span
          className={`text-13 max-md:line-clamp-2 md:block md:truncate ${fresh ? "font-medium text-stamp" : "text-ink"}`}
        >
          {title}
        </span>
        <span data-entry-meta="" className="block min-h-4 truncate text-12 text-ink-3 tabular-nums">
          {meta}
        </span>
      </Link>
      <span
        data-entry-chip=""
        className={`flex shrink-0 items-center justify-center ${chipWide ? "w-16" : "w-10"}`}
      >
        {chip}
      </span>
      <span
        data-entry-views=""
        style={{ width: `${viewsCh}ch` }}
        className="shrink-0 text-right text-12 text-ink-2 tabular-nums"
      >
        {formatNumber(views)}
        <span className="sr-only"> views</span>
      </span>
    </li>
  );
}
