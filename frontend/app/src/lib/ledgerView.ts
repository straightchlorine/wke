import type { ApiError } from "../api/generated";
import { isServerDown } from "./errors";
import {
  formatLiveEditsStatus,
  formatNumber,
  formatUtcClockSeconds,
  formatUtcTime,
} from "./format";
import type { LiveRow, LiveStreamState } from "./hooks/useLive";

/** How long the feed may stay down before the panel says it is disconnected instead of reconnecting. */
const DISCONNECT_NOTICE_MS = 5 * 60_000;
/** The minutes without an edit after which the panel says when the last edit came instead of counting minutes. */
const QUIET_SINCE_MIN = 10;

/** Returns true while the edit feed cannot supply edit figures, so a count of 0 would not be a measurement. */
export function feedIsDown(streamState: LiveStreamState): boolean {
  return streamState === "down" || streamState === "disconnected";
}

/** The states of the edit feed that screen readers are told about. */
export type FeedState = "connected" | "reconnecting" | "disconnected" | "paused" | "rate_limited";

/** Returns the state of the edit feed that screen readers are told about. */
export function announcedFeedState(feed: {
  rateLimited: boolean;
  streamState: LiveStreamState;
  paused: boolean;
}): FeedState {
  if (feed.rateLimited) {
    return "rate_limited";
  }
  if (feedIsDown(feed.streamState)) {
    return "disconnected";
  }
  if (feed.streamState === "reconnecting") {
    return "reconnecting";
  }
  return feed.paused ? "paused" : "connected";
}

/**
 * The state of the edit feed as one line. A "count" ("last 12") reads inline after the panel's
 * title, and a "notice" is a line of its own under it.
 */
export interface LedgerStatus {
  kind: "count" | "notice";
  text: string;
}

export interface LedgerStatusInput {
  paused: boolean;
  /** When the reader paused; null for a pause restored from an earlier visit. */
  pausedSince: Date | null;
  rateLimited: boolean;
  streamState: LiveStreamState;
  /** The cause of a "disconnected" state. */
  streamError: ApiError | null;
  lastEventAt: string | null;
  downSince: Date | null;
  /** How many edit rows the panel holds. */
  rowCount: number;
  /** The current time in milliseconds. */
  now: number;
}

const notice = (text: string): LedgerStatus => ({ kind: "notice", text });

/** Returns the status line of the edit feed and where it goes. */
export function ledgerStatus(input: LedgerStatusInput): LedgerStatus {
  const count = (): LedgerStatus => ({ kind: "count", text: `last ${input.rowCount}` });
  const lastHeard = input.lastEventAt ?? input.downSince;

  if (input.paused && !input.rateLimited) {
    return notice(
      input.pausedSince != null
        ? `Live edits paused since ${formatUtcTime(input.pausedSince)}`
        : "Live edits paused",
    );
  }
  if (input.rateLimited) {
    return notice(formatLiveEditsStatus("rate_limited"));
  }
  if (input.streamState === "down") {
    return notice(
      lastHeard && input.now - new Date(lastHeard).getTime() >= DISCONNECT_NOTICE_MS
        ? formatLiveEditsStatus("disconnected", lastHeard)
        : formatLiveEditsStatus("reconnecting"),
    );
  }
  if (input.streamState === "disconnected") {
    return notice(
      input.streamError
        ? `Live edits disconnected: ${isServerDown(input.streamError) ? "the server is unavailable" : input.streamError.detail}`
        : formatLiveEditsStatus("disconnected"),
    );
  }
  if (input.streamState === "reconnecting") {
    return notice(formatLiveEditsStatus("reconnecting"));
  }
  if (!input.lastEventAt) {
    return count();
  }
  const idleMin = Math.floor((input.now - new Date(input.lastEventAt).getTime()) / 60_000);
  if (idleMin >= QUIET_SINCE_MIN) {
    return notice(`quiet since ${formatUtcTime(input.lastEventAt)}`);
  }
  return idleMin >= 1
    ? notice(`last ${input.rowCount}, listening, quiet for ${idleMin} min`)
    : count();
}

/**
 * Returns the figure and the line under it for the edits seen since the page loaded.
 * The edits replayed on load are not counted, so until the first edit lands the line says when listening began, and after that how many minutes the count covers.
 * The line is empty while the edit feed is unavailable.
 */
export function editsSeenCounter(input: {
  unavailable: boolean;
  count: number;
  loadTime: Date;
  /** The current time in milliseconds. */
  now: number;
}): { value: string; sub: string } {
  if (input.unavailable) {
    return { value: "no edit data", sub: "" };
  }
  const minutes = Math.max(1, Math.round((input.now - input.loadTime.getTime()) / 60_000));
  return {
    value: formatNumber(input.count),
    sub: input.count === 0 ? `since ${formatUtcTime(input.loadTime)}` : `in ${minutes} min`,
  };
}

/** Returns the text of the marker row, which separates the edits that arrived live from the replayed ones. */
export function ledgerMarkerLabel(input: {
  editsUnavailable: boolean;
  disconnectedSince: string | Date | null;
  paused: boolean;
  pausedSince: Date | null;
  resumedAt: Date | null;
  loadTime: Date;
}): string {
  if (input.editsUnavailable) {
    return `no live edits${input.disconnectedSince ? `, disconnected since ${formatUtcTime(input.disconnectedSince)}` : ""}`;
  }
  if (input.paused && input.pausedSince == null) {
    return "live edits paused";
  }
  return `listening since ${formatUtcClockSeconds(input.resumedAt ?? input.loadTime)} UTC`;
}

/** What the panel shows of the rows: those that fit, the count that does not, and where the marker row goes. */
export interface LedgerWindow {
  shownRows: LiveRow[];
  /** Arrivals that are not shown as rows, for the "+N more" row. */
  moreCount: number;
  markerIndex: number;
}

function arrivals(rows: LiveRow[]): number {
  return rows.reduce((sum, row) => sum + (row.isArrival ? row.runCount : 0), 0);
}

/**
 * Fits the rows into the slots. The marker row sits at the first replayed row, or after the last
 * shown row when every row is an arrival. Rows are newest first, so arrivals are at the top.
 */
export function ledgerWindow(input: {
  rows: LiveRow[];
  editsSeenSincePageLoad: number;
  /** All slots of the panel, including the marker row. */
  slots: number;
  hasNotice: boolean;
}): LedgerWindow {
  // Arrivals beyond the slots fold into the "+N more" row, which then takes a slot of its own.
  const moreBase = Math.max(0, input.editsSeenSincePageLoad - arrivals(input.rows));
  const capacity = input.slots - 1 - (input.hasNotice ? 1 : 0);
  const fits = moreBase > 0 || arrivals(input.rows.slice(capacity)) > 0 ? capacity - 1 : capacity;
  const shownRows = input.rows.slice(0, fits);
  const firstReplayed = input.rows.findIndex((row) => !row.isArrival);
  return {
    shownRows,
    moreCount: moreBase + arrivals(input.rows.slice(fits)),
    markerIndex: firstReplayed === -1 ? shownRows.length : firstReplayed,
  };
}
