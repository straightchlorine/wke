import { useEffect, useRef, useState } from "react";
import { getLive } from "../../api/generated";
import type { EditEvent, LiveResponse, ApiError } from "../../api/generated";
import { unwrap } from "../../api/queries";
import { toProblem } from "../errors";
import { newestOfBurst, orderLedgerRows } from "../ledgerOrder";
import { startVisiblePoll } from "./startVisiblePoll";

/**
 * The API's stream state, plus "disconnected" when this client could not read a poll response at all.
 * `streamError` holds the cause.
 */
export type LiveStreamState = LiveResponse["stream"] | "disconnected";

export interface LiveTopicRef {
  pageId: number;
  slug: string;
}

export interface LiveRow {
  /** The new revision id of the newest edit behind this row. It changes whenever another edit joins the row. */
  key: string;
  ts: string;
  /** The newest edit's cursor, which breaks ties between rows of the same second. */
  cursor: number;
  title: string;
  pageId: number | null;
  slug: string | null;
  byteDelta: number | null;
  userKind: EditEvent["user_kind"];
  /** Number of edits merged into this row. It stays 1 until another edit of the same title arrives. */
  runCount: number;
  /** True for a row that arrived live, false for one replayed on load or on resume. */
  isArrival: boolean;
}

export interface UseLiveOptions {
  /** Injectable for tests; defaults to the generated getLive call. */
  fetchLive?: (since: number | undefined) => Promise<LiveResponse>;
  /** Resolves an edit's title to a tracked topic, which supplies the page id and slug used to link and ping the row. */
  resolveTopic?: (title: string) => LiveTopicRef | undefined;
  /**
   * Called with the page id of each edit, to ping its node in the concept graph. Ids that are not in the graph are ignored.
   * `ring` is false to ping the node without the ring animation.
   */
  onPing?: (pageId: number, ring: boolean) => void;
  paused?: boolean;
  reducedMotion?: boolean;
  /** Poll cadence while the tab is visible. A hidden tab schedules no further polls, and one runs at once when it is shown again. */
  visibleIntervalMs?: number;
  staggerMs?: number;
  maxRows?: number;
  /** Most arrivals from one poll that are shown. The oldest of a larger burst are dropped and counted in `overflowCount`. */
  ringBurstLimit?: number;
  enabled?: boolean;
}

export interface UseLiveResult {
  rows: LiveRow[];
  editsSeenSincePageLoad: number;
  loadTime: Date;
  streamState: LiveStreamState;
  /** The cause of a "disconnected" state; null otherwise. */
  streamError: ApiError | null;
  lastEventAt: string | null;
  counters: LiveResponse["counters"] | null;
  /** When the stream was first seen down; null while it is not down. */
  downSince: Date | null;
  /**
   * True while the API's limiter is refusing polls (429). The rows and
   * counters stay as they were; the next poll waits out Retry-After.
   */
  rateLimited: boolean;
  /** Arrivals queued while paused, inserted together on resume. */
  missedWhilePaused: number;
  /** Number of arrivals from the latest poll that exceeded `ringBurstLimit` and were not shown. */
  overflowCount: number;
}

const DEFAULTS = {
  visibleIntervalMs: 20_000,
  staggerMs: 1_400,
  maxRows: 7,
  ringBurstLimit: 3,
};
const REPLAY_WINDOW_MS = 2_000;
/** Lower and upper limits on the wait after a 429, whatever Retry-After says. */
const RATE_LIMIT_MIN_RETRY_MS = 5_000;
const RATE_LIMIT_MAX_RETRY_MS = 120_000;
/** How recent an edit queued during a pause must be to ring its node when the pause ends. */
const PING_HOLD_MS = 60_000;

const COUNTERS_STORAGE_KEY = "wke-live-counters";

function isCounters(value: unknown): value is LiveResponse["counters"] {
  return (
    typeof value === "object" &&
    value !== null &&
    "dossiers_built_today" in value &&
    typeof value.dossiers_built_today === "number" &&
    "enwiki_edits_last_hour" in value &&
    "topics_tracked" in value
  );
}

/** The counters from this tab's last good poll if they are from today (UTC), so a refused first poll still has figures to show. */
function readStoredCounters(): LiveResponse["counters"] | null {
  try {
    const raw =
      typeof window === "undefined" ? null : window.sessionStorage.getItem(COUNTERS_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !("day" in parsed) ||
      !("counters" in parsed)
    ) {
      return null;
    }
    return parsed.day === today() && isCounters(parsed.counters) ? parsed.counters : null;
  } catch {
    return null;
  }
}

function storeCounters(counters: LiveResponse["counters"]) {
  try {
    window.sessionStorage.setItem(COUNTERS_STORAGE_KEY, JSON.stringify({ day: today(), counters }));
  } catch {
    // Storage is unavailable or full: the counters simply are not kept.
  }
}

const ROWS_STORAGE_KEY = "wke-live-rows";
const EDITS_SEEN_STORAGE_KEY = "wke-live-edits-seen";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function isRow(value: unknown): value is LiveRow {
  return (
    typeof value === "object" &&
    value !== null &&
    "key" in value &&
    typeof value.key === "string" &&
    "title" in value &&
    typeof value.title === "string" &&
    "ts" in value &&
    typeof value.ts === "string" &&
    "cursor" in value &&
    typeof value.cursor === "number"
  );
}

/** The rows from this tab's last good poll if they are from today (UTC), marked as replayed. */
function readStoredRows(): LiveRow[] {
  try {
    const raw =
      typeof window === "undefined" ? null : window.sessionStorage.getItem(ROWS_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !("day" in parsed) ||
      !("rows" in parsed)
    ) {
      return [];
    }
    return parsed.day === today() && Array.isArray(parsed.rows)
      ? parsed.rows.filter(isRow).map((row) => ({ ...row, isArrival: false }))
      : [];
  } catch {
    return [];
  }
}

function storeRows(rows: LiveRow[]) {
  try {
    window.sessionStorage.setItem(ROWS_STORAGE_KEY, JSON.stringify({ day: today(), rows }));
  } catch {
    // Storage is unavailable or full: the rows simply are not kept.
  }
}

/** Returns the edits-seen count stored by this page load, or 0 when another page load stored it. A reload therefore starts at 0. */
function readStoredEditsSeen(): number {
  try {
    const raw =
      typeof window === "undefined" ? null : window.sessionStorage.getItem(EDITS_SEEN_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !("origin" in parsed) ||
      !("count" in parsed)
    ) {
      return 0;
    }
    return parsed.origin === performance.timeOrigin && typeof parsed.count === "number"
      ? parsed.count
      : 0;
  } catch {
    return 0;
  }
}

function storeEditsSeen(count: number) {
  try {
    window.sessionStorage.setItem(
      EDITS_SEEN_STORAGE_KEY,
      JSON.stringify({ origin: performance.timeOrigin, count }),
    );
  } catch {
    // Storage is unavailable or full: the count simply is not kept.
  }
}

async function defaultFetchLive(since: number | undefined): Promise<LiveResponse> {
  return unwrap(await getLive({ query: since === undefined ? {} : { since } }));
}

function byTsAscending(events: EditEvent[]): EditEvent[] {
  // The API orders same-second events by cursor descending; break ties by
  // cursor ascending so they end up in arrival order, not reversed.
  return events.toSorted(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime() || a.cursor - b.cursor,
  );
}

interface InsertOptions {
  /** Whether the events may ring their nodes at all. */
  ring: boolean;
  /** Whether the rows count as live arrivals. */
  countable: boolean;
  /** When set, only events at or after this time in milliseconds ring. */
  cutoffForRing?: number;
}

interface Ping {
  pageId: number;
  ring: boolean;
}

/** Merges events into the rows, one after the other, and returns the new rows and the pings the events call for. */
function mergeEvents(
  rows: LiveRow[],
  events: EditEvent[],
  opts: InsertOptions,
  resolveTopic: UseLiveOptions["resolveTopic"],
  maxRows: number,
): { rows: LiveRow[]; pings: Ping[] } {
  let next = rows;
  const pings: Ping[] = [];
  for (const event of events) {
    const topic = resolveTopic?.(event.title);
    const pageId = topic?.pageId ?? event.page_id ?? null;
    const existing = next.find((row) => row.title === event.title);
    if (existing) {
      const merged: LiveRow = {
        ...existing,
        key: String(event.rev_new),
        ts: event.ts,
        cursor: event.cursor,
        byteDelta:
          existing.byteDelta != null && event.byte_delta != null
            ? existing.byteDelta + event.byte_delta
            : (event.byte_delta ?? existing.byteDelta),
        userKind: event.user_kind,
        runCount: existing.runCount + 1,
        isArrival: opts.countable,
      };
      next = [merged, ...next.filter((row) => row !== existing)];
    } else {
      const row: LiveRow = {
        key: String(event.rev_new),
        ts: event.ts,
        cursor: event.cursor,
        title: event.title,
        pageId,
        slug: topic?.slug ?? null,
        byteDelta: event.byte_delta ?? null,
        userKind: event.user_kind,
        runCount: 1,
        isArrival: opts.countable,
      };
      next = [row, ...next];
    }
    if (pageId != null) {
      const ring =
        opts.ring &&
        (opts.cutoffForRing == null || new Date(event.ts).getTime() >= opts.cutoffForRing);
      pings.push({ pageId, ring });
    }
  }
  // Live arrivals stay above replayed rows, and each group is newest first.
  // Inserting at the front alone would put a replayed row above an arrival.
  return { rows: orderLedgerRows(next).slice(0, maxRows), pings };
}

/**
 * Polls `GET /api/v1/live` and returns the rows of Home's live edit list, the counters and the stream state.
 * The first response fills the rows as a replay and does not add to `editsSeenSincePageLoad`.
 * While paused, edits are counted and queued, then inserted together on resume.
 */
export function useLive(options: UseLiveOptions = {}): UseLiveResult {
  const config = { ...DEFAULTS, ...options };
  const optionsRef = useRef(config);
  // The polling effect and the timers read the latest options through this ref. A changed option
  // therefore does not restart them.
  useEffect(() => {
    optionsRef.current = config;
  });

  // The rows and the edits-seen count start from sessionStorage, so Home still shows them when it is
  // refused with a 429 on arrival or revisited from another page.
  const [rows, setRows] = useState<LiveRow[]>(readStoredRows);
  const [editsSeenSincePageLoad, setEditsSeenSincePageLoad] = useState(readStoredEditsSeen);
  const [streamState, setStreamState] = useState<LiveStreamState>("connected");
  const [streamError, setStreamError] = useState<ApiError | null>(null);
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);
  const [counters, setCounters] = useState<LiveResponse["counters"] | null>(readStoredCounters);
  const [downSince, setDownSince] = useState<Date | null>(null);
  const [rateLimited, setRateLimited] = useState(false);
  const [missedWhilePaused, setMissedWhilePaused] = useState(0);
  const [overflowCount, setOverflowCount] = useState(0);

  const loadTimeRef = useRef(new Date());
  const seenRef = useRef<Set<number>>(new Set());
  const cursorRef = useRef<number | undefined>(undefined);
  const firstPollRef = useRef(true);
  const pendingWhilePausedRef = useRef<EditEvent[]>([]);
  const wasPausedRef = useRef(config.paused ?? false);
  const timeoutsRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  // The latest rows. Staggered inserts can run before React has rendered the previous one, so state alone would be stale.
  const rowsRef = useRef(rows);

  function commitRows(next: LiveRow[]) {
    rowsRef.current = next;
    setRows(next);
  }

  function insertEvents(events: EditEvent[], opts: InsertOptions) {
    const { resolveTopic, onPing, maxRows } = optionsRef.current;
    const merged = mergeEvents(rowsRef.current, events, opts, resolveTopic, maxRows);
    commitRows(merged.rows);
    for (const ping of merged.pings) {
      onPing?.(ping.pageId, ping.ring);
    }
  }

  useEffect(() => {
    if (rows.length > 0) {
      storeRows(rows);
    }
  }, [rows]);

  useEffect(() => {
    storeEditsSeen(editsSeenSincePageLoad);
  }, [editsSeenSincePageLoad]);

  function schedule(fn: () => void, delayMs: number) {
    const { reducedMotion = false } = optionsRef.current;
    const t = setTimeout(fn, reducedMotion ? 0 : delayMs);
    timeoutsRef.current.push(t);
  }

  function handleResponse(response: LiveResponse) {
    const { staggerMs, ringBurstLimit } = optionsRef.current;
    cursorRef.current = response.cursor;
    setRateLimited(false);
    setStreamState(response.stream);
    setStreamError(null);
    setLastEventAt(response.last_event_at ?? null);
    if (response.stream === "down") {
      setDownSince((prev) => prev ?? new Date());
    } else {
      setDownSince(null);
    }
    // The counters are kept even when the stream is down, because the built-today figure does not come from the stream.
    setCounters(response.counters);
    storeCounters(response.counters);

    // Clear the first-poll flag before the early return below. An empty first
    // response still counts as the first poll, so later edits are live
    // arrivals, not a replay.
    const isFirstPoll = firstPollRef.current;
    firstPollRef.current = false;

    const events = byTsAscending(response.edits).filter(
      (event) => !seenRef.current.has(event.rev_new),
    );
    for (const event of events) {
      seenRef.current.add(event.rev_new);
    }
    if (events.length === 0) {
      return;
    }

    if (isFirstPoll) {
      // The kept rows give way to the fresh replay instead of merging into it.
      commitRows([]);
      // Replayed edits are spread over REPLAY_WINDOW_MS. They ping the graph but are not counted or marked as arrivals.
      const spacing = events.length > 1 ? REPLAY_WINDOW_MS / (events.length - 1) : 0;
      const pausedNow = optionsRef.current.paused ?? false;
      events.forEach((event, index) => {
        schedule(
          () => insertEvents([event], { ring: !pausedNow, countable: false }),
          index * spacing,
        );
      });
      return;
    }

    setEditsSeenSincePageLoad((n) => n + events.length);

    if (optionsRef.current.paused) {
      pendingWhilePausedRef.current.push(...events);
      setMissedWhilePaused((n) => n + events.length);
      return;
    }

    const overflow = events.length > ringBurstLimit ? events.length - ringBurstLimit : 0;
    setOverflowCount(overflow);
    const toShow = newestOfBurst(events, ringBurstLimit);
    toShow.forEach((event, index) => {
      schedule(() => insertEvents([event], { ring: true, countable: true }), index * staggerMs);
    });
    if (overflow > 0) {
      schedule(() => setOverflowCount(0), toShow.length * staggerMs + staggerMs);
    }
  }

  // When the pause ends, the edits queued during it are inserted together as
  // replayed rows. Only those from the last PING_HOLD_MS ring their nodes.
  useEffect(() => {
    const isPaused = config.paused ?? false;
    if (wasPausedRef.current && !isPaused && pendingWhilePausedRef.current.length > 0) {
      const queued = pendingWhilePausedRef.current;
      pendingWhilePausedRef.current = [];
      setMissedWhilePaused(0);
      insertEvents(byTsAscending(queued), {
        ring: true,
        countable: false,
        cutoffForRing: Date.now() - PING_HOLD_MS,
      });
    }
    wasPausedRef.current = isPaused;
    // The effect runs only when `paused` changes. insertEvents reads the current options through optionsRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.paused]);

  useEffect(() => {
    if (options.enabled === false) {
      return undefined;
    }
    const stopPolling = startVisiblePoll(async (signal) => {
      let nextDelayMs = optionsRef.current.visibleIntervalMs;
      try {
        const { fetchLive = defaultFetchLive } = optionsRef.current;
        const response = await fetchLive(cursorRef.current);
        if (!signal.aborted) {
          handleResponse(response);
        }
      } catch (err) {
        // A thrown error means no usable LiveResponse arrived: a network failure, an API error or a body that is not JSON.
        if (!signal.aborted) {
          const problem = toProblem(err);
          if (problem.status === 429 || problem.code === "rate_limited") {
            // The API answered, so the client is not disconnected. The limiter,
            // not the feed, refused: keep what is on screen and wait out Retry-After.
            setRateLimited(true);
            setStreamState((state) => (state === "disconnected" ? "connected" : state));
            setStreamError(null);
            const waitMs = (problem.retry_after ?? 0) * 1000;
            nextDelayMs = Math.min(
              Math.max(waitMs, RATE_LIMIT_MIN_RETRY_MS),
              RATE_LIMIT_MAX_RETRY_MS,
            );
          } else {
            setRateLimited(false);
            setStreamState("disconnected");
            setStreamError(problem);
          }
        }
      }
      return nextDelayMs;
    });
    return () => {
      stopPolling();
      for (const t of timeoutsRef.current) {
        clearTimeout(t);
      }
      timeoutsRef.current = [];
    };
    // The effect restarts only when `enabled` changes. Every other option is read through optionsRef when it is needed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.enabled]);

  return {
    rows,
    editsSeenSincePageLoad,
    loadTime: loadTimeRef.current,
    streamState,
    streamError,
    lastEventAt,
    counters,
    downSince,
    rateLimited,
    missedWhilePaused,
    overflowCount,
  };
}
