/** The fields of a live-edit row that the display order reads. */
export interface OrderedRow {
  ts: string;
  cursor: number;
  /** True for a row that arrived live; false for one replayed on load. */
  isArrival: boolean;
}

/**
 * Returns a new list with live arrivals above the rows replayed on load, each group newest first,
 * and rows with the same timestamp ordered by higher cursor first.
 */
export function orderLedgerRows<T extends OrderedRow>(rows: readonly T[]): T[] {
  return rows.toSorted(
    (a, b) =>
      Number(b.isArrival) - Number(a.isArrival) ||
      new Date(b.ts).getTime() - new Date(a.ts).getTime() ||
      b.cursor - a.cursor,
  );
}

/**
 * Returns the last `limit` events of a burst sorted oldest first, so any events left out are the
 * oldest.
 */
export function newestOfBurst<T>(events: readonly T[], limit: number): T[] {
  return events.slice(Math.max(0, events.length - limit));
}
