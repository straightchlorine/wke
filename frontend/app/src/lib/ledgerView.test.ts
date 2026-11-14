import { describe, expect, it } from "vitest";
import type { ApiError } from "../api/generated";
import type { LiveRow, LiveStreamState } from "./hooks/useLive";
import {
  announcedFeedState,
  editsSeenCounter,
  feedIsDown,
  ledgerMarkerLabel,
  ledgerStatus,
  ledgerWindow,
  type LedgerStatusInput,
} from "./ledgerView";

const NOW = Date.parse("2026-11-10T12:00:00Z");
const minutesAgo = (n: number) => new Date(NOW - n * 60_000).toISOString();

function row(runCount: number, isArrival: boolean): LiveRow {
  return {
    key: String(Math.random()),
    ts: minutesAgo(0),
    cursor: 1,
    title: "T",
    pageId: 1,
    slug: "T",
    byteDelta: 1,
    userKind: "registered",
    runCount,
    isArrival,
  };
}

const base: LedgerStatusInput = {
  paused: false,
  pausedSince: null,
  rateLimited: false,
  streamState: "connected",
  streamError: null,
  lastEventAt: null,
  downSince: null,
  rowCount: 7,
  now: NOW,
};

function problem(over: Partial<ApiError>): ApiError {
  return {
    type: "about:blank",
    title: "t",
    status: 500,
    code: "internal",
    request_id: "",
    detail: "boom",
    ...over,
  };
}

describe("feedIsDown", () => {
  it.each<[LiveStreamState, boolean]>([
    ["down", true],
    ["disconnected", true],
    ["reconnecting", false],
    ["connected", false],
  ])("is %s -> %s", (state, expected) => {
    expect(feedIsDown(state)).toBe(expected);
  });
});

describe("announcedFeedState", () => {
  it.each([
    [{ rateLimited: true, streamState: "down", paused: true }, "rate_limited"],
    [{ rateLimited: false, streamState: "down", paused: true }, "disconnected"],
    [{ rateLimited: false, streamState: "disconnected", paused: false }, "disconnected"],
    [{ rateLimited: false, streamState: "reconnecting", paused: true }, "reconnecting"],
    [{ rateLimited: false, streamState: "connected", paused: true }, "paused"],
    [{ rateLimited: false, streamState: "connected", paused: false }, "connected"],
  ] as const)("%j -> %s", (feed, expected) => {
    expect(announcedFeedState(feed)).toBe(expected);
  });
});

describe("ledgerStatus", () => {
  it.each<[string, Partial<LedgerStatusInput>, string, string]>([
    [
      "paused since a time",
      { paused: true, pausedSince: new Date("2026-11-10T11:30:00Z") },
      "notice",
      "Live edits paused since 11:30 UTC",
    ],
    ["paused from an earlier visit", { paused: true }, "notice", "Live edits paused"],
    [
      "rate limited beats paused",
      { paused: true, rateLimited: true },
      "notice",
      "Live edits paused, retrying shortly",
    ],
    [
      "down for a short while",
      { streamState: "down", lastEventAt: minutesAgo(4) },
      "notice",
      "Live edits reconnecting",
    ],
    ["down with no time at all", { streamState: "down" }, "notice", "Live edits reconnecting"],
    [
      "down for five minutes",
      { streamState: "down", lastEventAt: minutesAgo(5) },
      "notice",
      "Live edits disconnected since 11:55 UTC",
    ],
    [
      "down since a Date",
      { streamState: "down", downSince: new Date(NOW - 6 * 60_000) },
      "notice",
      "Live edits disconnected since 11:54 UTC",
    ],
    [
      "disconnected without a cause",
      { streamState: "disconnected" },
      "notice",
      "Live edits disconnected",
    ],
    [
      "disconnected by an API error",
      { streamState: "disconnected", streamError: problem({ status: 401, detail: "no key" }) },
      "notice",
      "Live edits disconnected: no key",
    ],
    [
      "disconnected, server down",
      { streamState: "disconnected", streamError: problem({ status: 503 }) },
      "notice",
      "Live edits disconnected: the server is unavailable",
    ],
    ["reconnecting", { streamState: "reconnecting" }, "notice", "Live edits reconnecting"],
    ["no edit yet", {}, "count", "last 7"],
    ["last edit seconds ago", { lastEventAt: minutesAgo(0.5) }, "count", "last 7"],
    [
      "quiet for a minute",
      { lastEventAt: minutesAgo(1) },
      "notice",
      "last 7, listening, quiet for 1 min",
    ],
    [
      "quiet for nine minutes",
      { lastEventAt: minutesAgo(9.9) },
      "notice",
      "last 7, listening, quiet for 9 min",
    ],
    ["quiet for ten minutes", { lastEventAt: minutesAgo(10) }, "notice", "quiet since 11:50 UTC"],
  ])("%s", (_name, over, kind, text) => {
    expect(ledgerStatus({ ...base, ...over })).toEqual({ kind, text });
  });
});

describe("editsSeenCounter", () => {
  const loadTime = new Date(NOW - 7 * 60_000);
  it.each([
    ["unavailable feed", { unavailable: true, count: 5 }, { value: "no edit data", sub: "" }],
    ["no edit yet", { unavailable: false, count: 0 }, { value: "0", sub: "since 11:53 UTC" }],
    ["edits seen", { unavailable: false, count: 1234 }, { value: "1,234", sub: "in 7 min" }],
  ])("%s", (_name, input, expected) => {
    expect(editsSeenCounter({ ...input, loadTime, now: NOW })).toEqual(expected);
  });

  it("counts at least one minute", () => {
    const sub = editsSeenCounter({
      unavailable: false,
      count: 3,
      loadTime: new Date(NOW),
      now: NOW,
    }).sub;
    expect(sub).toBe("in 1 min");
  });
});

describe("ledgerMarkerLabel", () => {
  const input = {
    editsUnavailable: false,
    disconnectedSince: null,
    paused: false,
    pausedSince: null,
    resumedAt: null,
    loadTime: new Date("2026-11-10T11:53:20Z"),
  };
  it.each([
    [
      "unavailable, time known",
      { editsUnavailable: true, disconnectedSince: "2026-11-10T11:40:00Z" },
      "no live edits, disconnected since 11:40 UTC",
    ],
    ["unavailable, time unknown", { editsUnavailable: true }, "no live edits"],
    ["paused from an earlier visit", { paused: true }, "live edits paused"],
    [
      "paused on this page",
      { paused: true, pausedSince: new Date(NOW) },
      "listening since 11:53:20 UTC",
    ],
    ["resumed", { resumedAt: new Date("2026-11-10T11:58:01Z") }, "listening since 11:58:01 UTC"],
    ["listening", {}, "listening since 11:53:20 UTC"],
  ])("%s", (_name, over, expected) => {
    expect(ledgerMarkerLabel({ ...input, ...over })).toBe(expected);
  });
});

describe("ledgerWindow", () => {
  const live = [row(2, true), row(1, true), row(1, false), row(1, false)];
  it.each([
    ["all rows fit", { slots: 9, hasNotice: false, seen: 3 }, 4, 0, 2],
    ["a notice takes a slot", { slots: 5, hasNotice: true, seen: 3 }, 3, 0, 2],
    [
      "arrivals counted but not listed make a more row",
      { slots: 9, hasNotice: false, seen: 10 },
      4,
      7,
      2,
    ],
    ["the more row takes a slot", { slots: 4, hasNotice: false, seen: 4 }, 2, 1, 2],
  ])("%s", (_name, input, shown, more, marker) => {
    const w = ledgerWindow({
      rows: live,
      editsSeenSincePageLoad: input.seen,
      slots: input.slots,
      hasNotice: input.hasNotice,
    });
    expect([w.shownRows.length, w.moreCount, w.markerIndex]).toEqual([shown, more, marker]);
  });

  it("folds arrivals that do not fit into the more row", () => {
    const w = ledgerWindow({
      rows: [row(2, true), row(1, true), row(3, true), row(1, false)],
      editsSeenSincePageLoad: 6,
      slots: 3,
      hasNotice: false,
    });
    expect([w.shownRows.length, w.moreCount]).toEqual([1, 4]);
  });

  it("reserves a slot for the more row when an arrival falls past the capacity", () => {
    const rows = [row(1, true), row(1, true), row(1, true), row(1, true)];
    const slots = 4;
    const w = ledgerWindow({ rows, editsSeenSincePageLoad: 4, slots, hasNotice: true });
    const marker = 1;
    const notice = 1;
    const moreRow = w.moreCount > 0 ? 1 : 0;
    expect(w.shownRows.length + moreRow + marker + notice).toBeLessThanOrEqual(slots);
    expect(w.shownRows.length + w.moreCount).toBe(4);
  });

  it("reserves no slot for the more row when only replayed rows are past the capacity", () => {
    const rows = [row(1, true), row(1, false), row(1, false), row(1, false)];
    const w = ledgerWindow({ rows, editsSeenSincePageLoad: 1, slots: 4, hasNotice: true });
    expect([w.shownRows.length, w.moreCount]).toEqual([2, 0]);
  });

  it("reserves no slot for the more row when the rows exactly fill the capacity", () => {
    const rows = [row(1, true), row(1, true)];
    const w = ledgerWindow({ rows, editsSeenSincePageLoad: 2, slots: 4, hasNotice: true });
    expect([w.shownRows.length, w.moreCount]).toEqual([2, 0]);
  });

  it("puts the marker after the last shown row when every row is an arrival", () => {
    const w = ledgerWindow({
      rows: [row(1, true), row(1, true)],
      editsSeenSincePageLoad: 2,
      slots: 9,
      hasNotice: false,
    });
    expect(w.markerIndex).toBe(2);
  });
});
