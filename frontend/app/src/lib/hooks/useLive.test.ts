import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useLive } from "./useLive";
import type { EditEvent, LiveResponse } from "../../api/generated";

function edit(overrides: Partial<EditEvent>): EditEvent {
  return {
    cursor: 1,
    page_id: 100,
    title: "Alan Turing",
    rev_new: 1,
    ts: "2026-09-28T10:00:00Z",
    user_kind: "registered",
    byte_delta: 10,
    ...overrides,
  };
}

function response(overrides: Partial<LiveResponse>): LiveResponse {
  return {
    stream: "connected",
    server_time: "2026-09-28T10:00:00Z",
    cursor: 1,
    edits: [],
    counters: {
      enwiki_edits_last_hour: 0,
      tracked_edits_last_hour: 0,
      window_complete: true,
      dossiers_built_today: 10,
      topics_tracked: 40,
    },
    ...overrides,
  };
}

const VISIBLE_INTERVAL_MS = 1000;

function resolveTopic(title: string) {
  return title === "Alan Turing" ? { pageId: 999, slug: "alan-turing" } : undefined;
}

/** A fetchLive whose request never answers. */
const never = () => new Promise<LiveResponse>(() => {});

/** A fetchLive that answers with each response in turn, then with empty ones. */
function sequence(...responses: LiveResponse[]) {
  let call = 0;
  return vi.fn(async () => responses[call++] ?? response({}));
}

/** Mounts useLive with a stored value already in sessionStorage and a request that never answers. */
function mountWithStorage(key: string, value: unknown) {
  window.sessionStorage.setItem(key, JSON.stringify(value));
  return renderHook(() => useLive({ fetchLive: never, visibleIntervalMs: VISIBLE_INTERVAL_MS }));
}

describe("useLive", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps the rows and the edits count of the last good poll when the next page load is refused with a 429", async () => {
    const now = new Date().toISOString();
    const first = vi.fn(async () =>
      response({ cursor: 2, edits: [edit({ rev_new: 1, cursor: 1, ts: now, title: "Replay A" })] }),
    );
    const mounted = renderHook(() =>
      useLive({ fetchLive: first, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(mounted.result.current.rows.map((r) => r.title)).toEqual(["Replay A"]);
    mounted.unmount();

    const refused = vi.fn(async () => {
      throw {
        type: "about:blank",
        title: "Too many requests",
        status: 429,
        code: "rate_limited",
        request_id: "r",
        retry_after: 30,
        detail: "12 per 1 minute",
      };
    });
    const remounted = renderHook(() =>
      useLive({ fetchLive: refused, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(remounted.result.current.rateLimited).toBe(true);
    expect(remounted.result.current.rows.map((r) => r.title)).toEqual(["Replay A"]);
    expect(remounted.result.current.counters?.dossiers_built_today).toBe(10);
  });

  it("replaces the kept rows with the replay of the first good poll instead of merging into them", async () => {
    const now = new Date().toISOString();
    const fetchLive = vi.fn(async () =>
      response({ cursor: 2, edits: [edit({ rev_new: 1, cursor: 1, ts: now, title: "Replay A" })] }),
    );
    const mounted = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    mounted.unmount();
    const again = renderHook(() => useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(again.result.current.rows).toHaveLength(1);
    expect(again.result.current.rows[0]?.runCount).toBe(1);
  });

  it("replays the first response without counting or inserting an arrival", async () => {
    const fetchLive = vi.fn(async () =>
      response({ edits: [edit({ rev_new: 1, title: "Alan Turing" })] }),
    );
    const onPing = vi.fn();

    const { result } = renderHook(() =>
      useLive({ fetchLive, onPing, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]?.title).toBe("Alan Turing");
    expect(result.current.rows[0]?.isArrival).toBe(false);
    expect(result.current.editsSeenSincePageLoad).toBe(0);
    expect(onPing).toHaveBeenCalledWith(100, true);
  });

  it("dedupes by revid: a repeated edit is neither re-counted nor re-rung", async () => {
    let call = 0;
    const responses = [
      response({ edits: [] }),
      response({ edits: [edit({ rev_new: 5, title: "Roblox", page_id: 200 })] }),
      response({ edits: [edit({ rev_new: 5, title: "Roblox", page_id: 200 })] }),
    ];
    const fetchLive = vi.fn(async () => responses[call++] ?? response({ edits: [] }));
    const onPing = vi.fn();

    const { result } = renderHook(() =>
      useLive({ fetchLive, onPing, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 1500);
    });
    expect(result.current.editsSeenSincePageLoad).toBe(1);
    expect(onPing).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
    });
    expect(result.current.editsSeenSincePageLoad).toBe(1);
    expect(onPing).toHaveBeenCalledTimes(1);
    expect(result.current.rows).toHaveLength(1);
  });

  it("staggers same-poll arrivals 1400 ms apart, newest on top", async () => {
    let call = 0;
    const responses = [
      response({ edits: [] }),
      response({
        edits: [
          edit({ rev_new: 10, title: "First", ts: "2026-09-28T10:00:00Z" }),
          edit({ rev_new: 11, title: "Second", ts: "2026-09-28T10:00:05Z" }),
        ],
      }),
    ];
    const fetchLive = vi.fn(async () => responses[call++] ?? response({ edits: [] }));

    const { result } = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // The poll at VISIBLE_INTERVAL_MS returns both edits. The first row is inserted at once and the second after the default stagger delay.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 100);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["First"]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["First"]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["Second", "First"]);
  });

  it("while paused, edits keep counting but do not insert rows or ring until resume", async () => {
    let call = 0;
    const responses = [
      response({ edits: [] }),
      response({
        edits: [edit({ rev_new: 20, title: "Paused Topic", ts: "2026-09-28T10:00:00Z" })],
      }),
    ];
    const fetchLive = vi.fn(async () => responses[call++] ?? response({ edits: [] }));
    const onPing = vi.fn();

    const { result, rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useLive({ fetchLive, onPing, paused, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      { initialProps: { paused: true } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 10);
    });

    expect(result.current.editsSeenSincePageLoad).toBe(1);
    expect(result.current.missedWhilePaused).toBe(1);
    expect(result.current.rows).toHaveLength(0);
    expect(onPing).not.toHaveBeenCalled();

    rerender({ paused: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]?.title).toBe("Paused Topic");
    expect(result.current.missedWhilePaused).toBe(0);
  });

  it("on resume inserts the queued edits together and rings only those inside the hold time", async () => {
    const young = new Date(Date.now() - 30_000).toISOString();
    const old = new Date(Date.now() - 120_000).toISOString();
    let call = 0;
    const responses = [
      response({ edits: [] }),
      response({
        edits: [
          edit({ rev_new: 30, title: "Old Topic", page_id: 2, ts: old, cursor: 1 }),
          edit({ rev_new: 31, title: "Young Topic", page_id: 1, ts: young, cursor: 2 }),
        ],
      }),
    ];
    const fetchLive = vi.fn(async () => responses[call++] ?? response({ edits: [] }));
    const onPing = vi.fn();
    const { result, rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useLive({ fetchLive, onPing, paused, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      { initialProps: { paused: true } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 10);
    });
    expect(result.current.missedWhilePaused).toBe(2);

    rerender({ paused: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.rows.map((r) => [r.title, r.isArrival])).toEqual([
      ["Young Topic", false],
      ["Old Topic", false],
    ]);
    expect(onPing.mock.calls).toEqual([
      [2, false],
      [1, true],
    ]);
  });

  it("rings a live arrival exactly once under StrictMode", async () => {
    let call = 0;
    const responses = [
      response({ edits: [] }),
      response({ edits: [edit({ rev_new: 40, title: "Roblox", page_id: 200 })] }),
    ];
    const fetchLive = vi.fn(async () => responses[call++] ?? response({ edits: [] }));
    const onPing = vi.fn();
    const { result } = renderHook(
      () => useLive({ fetchLive, onPing, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      { wrapper: StrictMode },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 100);
    });
    expect(result.current.rows).toHaveLength(1);
    expect(onPing).toHaveBeenCalledExactlyOnceWith(200, true);
  });

  it("keeps same-tick inserts of the replay: two replayed edits both land as rows", async () => {
    const fetchLive = vi.fn(async () =>
      response({
        edits: [
          edit({ rev_new: 50, title: "A", cursor: 1 }),
          edit({ rev_new: 51, title: "B", cursor: 2 }),
        ],
      }),
    );
    const { result } = renderHook(() =>
      useLive({ fetchLive, reducedMotion: true, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.rows.map((r) => r.title).toSorted()).toEqual(["A", "B"]);
  });

  it("collapses edits of one title into one row with their net byte change", async () => {
    const fetchLive = sequence(
      response({}),
      response({
        edits: [
          edit({ rev_new: 60, cursor: 1, byte_delta: 10, ts: "2026-09-28T10:00:00Z" }),
          edit({ rev_new: 61, cursor: 2, byte_delta: -4, ts: "2026-09-28T10:00:01Z" }),
        ],
      }),
    );
    const { result } = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 3000);
    });
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]).toMatchObject({ key: "61", runCount: 2, byteDelta: 6 });
  });

  it("shows only the newest edits of a burst and counts the rest as overflow until they are gone", async () => {
    const edits = [1, 2, 3, 4].map((n) =>
      edit({ rev_new: 70 + n, cursor: n, title: `T${n}`, ts: `2026-09-28T10:00:0${n}Z` }),
    );
    const fetchLive = sequence(response({}), response({ edits }));
    const { result } = renderHook(() =>
      useLive({ fetchLive, ringBurstLimit: 2, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 100);
    });
    expect(result.current.overflowCount).toBe(2);
    expect(result.current.editsSeenSincePageLoad).toBe(4);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["T4", "T3"]);
    expect(result.current.overflowCount).toBe(0);
  });

  it("keeps no more rows than maxRows, dropping the oldest", async () => {
    const edits = [1, 2, 3].map((n) =>
      edit({ rev_new: 80 + n, cursor: n, title: `T${n}`, ts: `2026-09-28T10:00:0${n}Z` }),
    );
    const { result } = renderHook(() =>
      useLive({
        fetchLive: sequence(response({ edits })),
        maxRows: 2,
        visibleIntervalMs: VISIBLE_INTERVAL_MS,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["T3", "T2"]);
  });

  it("does not poll when disabled", async () => {
    const fetchLive = sequence();
    renderHook(() => useLive({ fetchLive, enabled: false }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fetchLive).not.toHaveBeenCalled();
  });

  it("shows the rows of an earlier page as replayed, not as arrivals", async () => {
    const day = new Date().toISOString().slice(0, 10);
    const stored = { ...edit({}), key: "1", isArrival: true, runCount: 1, pageId: 100, slug: null };
    window.sessionStorage.setItem("wke-live-rows", JSON.stringify({ day, rows: [stored] }));
    const { result } = renderHook(() =>
      useLive({ fetchLive: never, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    expect(result.current.rows.map((r) => r.isArrival)).toEqual([false]);
  });

  it("remembers when the stream first went down until it is back", async () => {
    const fetchLive = sequence(
      response({ stream: "down" }),
      response({ stream: "down" }),
      response({ stream: "connected" }),
    );
    const { result } = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const since = result.current.downSince;
    expect(since).toBeInstanceOf(Date);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
    });
    expect(result.current.downSince).toBe(since);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
    });
    expect(result.current.downSince).toBeNull();
  });

  it.each([
    [undefined, 5000],
    [1, 5000],
    [30, 30_000],
    [1000, 120_000],
  ])("waits out a Retry-After of %s s as %s ms after a 429", async (retryAfter, waitMs) => {
    const fetchLive = vi.fn(async () => {
      throw { code: "rate_limited", status: 429, request_id: "", retry_after: retryAfter };
    });
    renderHook(() => useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(waitMs - 1);
    });
    expect(fetchLive).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(fetchLive).toHaveBeenCalledTimes(2);
  });

  describe("what a page load keeps in sessionStorage", () => {
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
    const row = {
      key: "1",
      ts: "2026-09-28T10:00:00Z",
      cursor: 1,
      title: "Kept",
      pageId: 100,
      slug: null,
      byteDelta: 1,
      userKind: "registered",
      runCount: 1,
      isArrival: true,
    };
    const counters = response({}).counters;

    it.each([
      ["today's rows", { day: today, rows: [row] }, ["Kept"]],
      ["yesterday's rows", { day: yesterday, rows: [row] }, []],
      ["rows without a title", { day: today, rows: [{ ...row, title: undefined }] }, []],
      ["something that is not rows", { day: today, rows: "x" }, []],
    ])("restores %s", (_name, stored, titles) => {
      const { result } = mountWithStorage("wke-live-rows", stored);
      expect(result.current.rows.map((r) => r.title)).toEqual(titles);
    });

    it.each([
      ["today's counters", { day: today, counters }, counters],
      ["yesterday's counters", { day: yesterday, counters }, null],
      [
        "counters of the wrong shape",
        { day: today, counters: { ...counters, dossiers_built_today: "x" } },
        null,
      ],
    ])("restores %s", (_name, stored, expected) => {
      const { result } = mountWithStorage("wke-live-counters", stored);
      expect(result.current.counters).toEqual(expected);
    });

    it.each([
      ["this page load", 0, 5],
      ["an earlier page load", -1, 0],
    ])("restores the edits seen by %s", (_name, originOffset, expected) => {
      const { result } = mountWithStorage("wke-live-edits-seen", {
        origin: performance.timeOrigin + originOffset,
        count: 5,
      });
      expect(result.current.editsSeenSincePageLoad).toBe(expected);
    });

    it("keeps the edits seen when the page is shown again", async () => {
      const fetchLive = sequence(
        response({}),
        response({ edits: [edit({ rev_new: 90, cursor: 1 }), edit({ rev_new: 91, cursor: 2 })] }),
      );
      const first = renderHook(() =>
        useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 100);
      });
      expect(first.result.current.editsSeenSincePageLoad).toBe(2);
      first.unmount();

      const again = renderHook(() =>
        useLive({ fetchLive: never, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      );
      expect(again.result.current.editsSeenSincePageLoad).toBe(2);
    });
  });

  it("links a row and its ping to the tracked topic of the title", async () => {
    const onPing = vi.fn();
    const { result } = renderHook(() =>
      useLive({
        fetchLive: sequence(response({ edits: [edit({ page_id: 100 })] })),
        resolveTopic,
        onPing,
        visibleIntervalMs: VISIBLE_INTERVAL_MS,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current.rows[0]).toMatchObject({ pageId: 999, slug: "alan-turing" });
    expect(onPing).toHaveBeenCalledWith(999, true);
  });

  it("reports when the last edit happened", async () => {
    const { result } = renderHook(() =>
      useLive({
        fetchLive: sequence(response({ last_event_at: "2026-09-28T09:59:00Z" })),
        visibleIntervalMs: VISIBLE_INTERVAL_MS,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.lastEventAt).toBe("2026-09-28T09:59:00Z");
  });

  it("keeps live arrivals above rows inserted as replayed ones, whatever their time", async () => {
    const now = Date.now();
    const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();
    const fetchLive = sequence(
      response({}),
      response({ edits: [edit({ rev_new: 100, title: "Live", ts: iso(-5000) })] }),
      response({ edits: [edit({ rev_new: 101, title: "Queued", ts: iso(-1000) })] }),
    );
    const { result, rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useLive({ fetchLive, paused, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      { initialProps: { paused: false } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 100);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["Live"]);

    rerender({ paused: true });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
    });
    rerender({ paused: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["Live", "Queued"]);
  });

  it("shows the highest cursor of a burst that fits only one row, as the newest of equal seconds", async () => {
    const fetchLive = sequence(
      response({}),
      response({
        edits: [
          edit({ rev_new: 110, title: "Low", cursor: 1, ts: "2026-09-28T10:00:00Z" }),
          edit({ rev_new: 111, title: "High", cursor: 2, ts: "2026-09-28T10:00:00Z" }),
        ],
      }),
    );
    const { result } = renderHook(() =>
      useLive({ fetchLive, ringBurstLimit: 1, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS + 3000);
    });
    expect(result.current.rows.map((r) => r.title)).toEqual(["High"]);
  });

  it("sets streamState disconnected with the error on a malformed poll, not reconnecting forever", async () => {
    const problem = {
      type: "about:blank",
      title: "Service unavailable",
      status: 502,
      code: "upstream_unavailable" as const,
      request_id: "",
      detail: "The API answered with text/html instead of JSON",
    };
    const fetchLive = vi.fn(async () => {
      throw problem;
    });

    const { result } = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.streamState).toBe("disconnected");
    expect(result.current.streamError).toEqual(problem);

    // Stays "disconnected", not "reconnecting", across further failed polls.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS * 3);
    });
    expect(result.current.streamState).toBe("disconnected");
  });

  it("a 429 after a disconnect clears the disconnected state and its error", async () => {
    let call = 0;
    const fetchLive = vi.fn(async () => {
      call += 1;
      if (call === 1) {
        throw { code: "internal", status: 0 };
      }
      throw { code: "rate_limited", status: 429, request_id: "", retry_after: 1 };
    });
    const { result } = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.streamState).toBe("disconnected");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
    });
    expect(result.current.rateLimited).toBe(true);
    expect(result.current.streamState).toBe("connected");
    expect(result.current.streamError).toBeNull();
  });

  it("clears streamError and reports the API's own state once a poll parses again", async () => {
    let call = 0;
    const fetchLive = vi.fn(async () => {
      call += 1;
      if (call === 1) {
        throw { code: "internal", status: 0 };
      }
      return response({ stream: "connected" });
    });

    const { result } = renderHook(() =>
      useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.streamState).toBe("disconnected");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
    });
    expect(result.current.streamState).toBe("connected");
    expect(result.current.streamError).toBeNull();
  });

  describe("hidden tab", () => {
    let state: DocumentVisibilityState = "visible";

    function setVisibility(next: DocumentVisibilityState) {
      state = next;
      document.dispatchEvent(new Event("visibilitychange"));
    }

    beforeEach(() => {
      state = "visible";
      vi.spyOn(document, "visibilityState", "get").mockImplementation(() => state);
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("schedules no poll after the tab hides, and polls at once when it returns", async () => {
      const fetchLive = vi.fn(async () => response({}));
      renderHook(() => useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchLive).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS - 100);
      });
      act(() => setVisibility("hidden"));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS * 10);
      });
      expect(fetchLive).toHaveBeenCalledTimes(1);

      await act(async () => {
        setVisibility("visible");
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchLive).toHaveBeenCalledTimes(2);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS);
      });
      expect(fetchLive).toHaveBeenCalledTimes(3);
    });

    it("makes no request after unmount, neither for an answer in flight nor when the tab returns", async () => {
      const pending: Array<(value: LiveResponse) => void> = [];
      const fetchLive = vi.fn(() => new Promise<LiveResponse>((r) => pending.push(r)));
      const { unmount } = renderHook(() =>
        useLive({ fetchLive, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      );
      unmount();
      await act(async () => {
        pending[0]?.(response({}));
        await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS * 3);
      });
      expect(fetchLive).toHaveBeenCalledTimes(1);

      const second = vi.fn(async () => response({}));
      const hiddenWait = renderHook(() =>
        useLive({ fetchLive: second, visibleIntervalMs: VISIBLE_INTERVAL_MS }),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      act(() => setVisibility("hidden"));
      hiddenWait.unmount();
      await act(async () => {
        setVisibility("visible");
        await vi.advanceTimersByTimeAsync(VISIBLE_INTERVAL_MS * 3);
      });
      expect(second).toHaveBeenCalledTimes(1);
    });
  });
});
