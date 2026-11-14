import { describe, expect, it } from "vitest";
import type { TrendingTopic } from "../api/generated";
import type { LiveRow } from "./hooks/useLive";
import { FRESH_EDIT_MS, freshPageIds, isBuilt, sortByViews, viewsColumnCh } from "./todaysIndex";

function topic(over: Partial<TrendingTopic>): TrendingTopic {
  return { rank: 1, page_id: 1, title: "T", views: 10, rev_id: 1, dossier_state: "none", ...over };
}

describe("isBuilt", () => {
  it.each([
    ["ready", true],
    ["partial", true],
    ["building", false],
    ["none", false],
  ] as const)("%s -> %s", (state, expected) => {
    expect(isBuilt(topic({ dossier_state: state }))).toBe(expected);
  });
});

describe("sortByViews", () => {
  it("puts the most read first and breaks a tie by the feed's rank, without changing the input", () => {
    const input = [
      topic({ page_id: 1, views: 5, rank: 3 }),
      topic({ page_id: 2, views: 9, rank: 4 }),
      topic({ page_id: 3, views: 5, rank: 2 }),
    ];
    expect(sortByViews(input).map((t) => t.page_id)).toEqual([2, 3, 1]);
    expect(input.map((t) => t.page_id)).toEqual([1, 2, 3]);
  });
});

describe("viewsColumnCh", () => {
  it.each([
    ["no topics", [], 5],
    ["short figures keep the minimum", [12, 999], 5],
    ["a comma counts half", [1_234_567], 8.25],
    ["the longest figure decides", [12_345, 1_234_567, 100], 8.25],
  ])("%s", (_name, views, expected) => {
    expect(viewsColumnCh(views.map((v) => topic({ views: v })))).toBe(expected);
  });
});

describe("freshPageIds", () => {
  const now = Date.parse("2026-11-10T12:00:00Z");
  const row = (pageId: number | null, msAgo: number): LiveRow => ({
    key: String(msAgo),
    ts: new Date(now - msAgo).toISOString(),
    cursor: 1,
    title: "T",
    pageId,
    slug: null,
    byteDelta: null,
    userKind: "bot",
    runCount: 1,
    isArrival: true,
  });

  it("keeps rows edited within the window and drops older rows and rows without a page", () => {
    const rows = [
      row(1, 0),
      row(2, FRESH_EDIT_MS - 1),
      row(3, FRESH_EDIT_MS),
      row(null, 1000),
      row(4, 5 * FRESH_EDIT_MS),
    ];
    expect([...freshPageIds(rows, now)]).toEqual([1, 2]);
  });
});
