import type { TrendingTopic } from "../api/generated";
import { formatNumber } from "./format";
import type { LiveRow } from "./hooks/useLive";

/** How long after an edit its article counts as freshly edited. */
export const FRESH_EDIT_MS = 60_000;

/** Returns true for a topic whose dossier exists, whether complete or partial. */
export function isBuilt(topic: TrendingTopic): boolean {
  return topic.dossier_state === "ready" || topic.dossier_state === "partial";
}

/**
 * Orders topics by views, most read first, as the list reads top to bottom.
 * The feed's own rank is not monotonic in views, so the row position is the rank.
 */
export function sortByViews(topics: TrendingTopic[]): TrendingTopic[] {
  return topics.toSorted((a, b) => b.views - a.views || a.rank - b.rank);
}

/**
 * Returns the width in `ch` of the views column: as wide as the longest figure, at least 5.
 * A digit is 1ch and a comma about half of that, plus a quarter ch of slack.
 */
export function viewsColumnCh(topics: TrendingTopic[]): number {
  return Math.max(
    5,
    ...topics.map((topic) => {
      const figure = formatNumber(topic.views);
      return figure.length - (figure.match(/,/g)?.length ?? 0) / 2 + 0.25;
    }),
  );
}

/** Returns the page ids of the rows that were edited within `FRESH_EDIT_MS` of `now`, in milliseconds. */
export function freshPageIds(rows: LiveRow[], now: number): Set<number> {
  const ids = new Set<number>();
  for (const row of rows) {
    if (row.pageId != null && now - new Date(row.ts).getTime() < FRESH_EDIT_MS) {
      ids.add(row.pageId);
    }
  }
  return ids;
}
