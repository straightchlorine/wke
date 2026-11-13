import { describe, expect, it } from "vitest";
import type { DossierView } from "../api/dossier";
import { loadDossier } from "../test/fixtures";
import { freshnessView, leftOutSummary, seedPin } from "./sourceRecord";

type Freshness = DossierView["freshness"];

function freshness(extra: Partial<Freshness>): Freshness {
  return { state: "fresh", pinned_rev_id: 1, checked_at: null, source: "watcher", ...extra };
}

describe("seedPin", () => {
  const dossier = loadDossier();
  const [first] = dossier.citations;

  it("is the pin of the seed citation", () => {
    const related = { ...first!, id: "r", role: "related" as const };
    const seed = { ...first!, id: "s", role: "seed" as const, pin: { ...first!.pin, rev_id: 7 } };
    expect(seedPin({ citations: [related, seed] })?.rev_id).toBe(7);
  });

  it("falls back to the first citation, and is undefined without any", () => {
    const related = { ...first!, role: "related" as const };
    expect(seedPin({ citations: [related] })).toBe(related.pin);
    expect(seedPin({ citations: [] })).toBeUndefined();
  });
});

describe("freshnessView", () => {
  it("passes the state through and leaves the tooltip to the chip when there is no freshness source", () => {
    expect(freshnessView(freshness({ state: "unknown", source: "none" }), true)).toEqual({
      state: "unknown",
      info: undefined,
    });
  });

  it.each([
    ["a fresh watcher state turns unknown", "fresh", "unknown"],
    ["a stale watcher state stays stale", "stale", "stale"],
  ] as const)("while the edit feed is down, %s", (_name, state, expected) => {
    const view = freshnessView(freshness({ state }), true);
    expect(view.state).toBe(expected);
    expect(view.info).toBe(
      "The edit feed is disconnected, so WKE cannot say whether this dossier is up to date.",
    );
  });

  it("trusts a polled result even while the edit feed is down", () => {
    const view = freshnessView(freshness({ source: "poll", checked_at: null }), true);
    expect(view.state).toBe("fresh");
    expect(view.info).toBe(
      "Not checked yet. WKE asks Wikipedia for the newest revision and compares it with the pinned one. The text below is still the pinned revision.",
    );
  });

  it("explains a watcher result in a sentence that starts with a capital", () => {
    const view = freshnessView(freshness({ checked_at: "2026-11-12T08:00:00Z" }), false);
    expect(view.state).toBe("fresh");
    expect(view.info).toMatch(
      /^Checked .+\. WKE compares the pinned revision with the newest edits it has seen\./,
    );
  });
});

describe("leftOutSummary", () => {
  it("counts both causes and gives one sentence for each, joined by semicolons", () => {
    expect(leftOutSummary(["List of films", "See also"], ["Legacy"], 2000)).toEqual({
      count: 3,
      detail:
        "No prose, so left out (lists and tables are not extracted): List of films; See also. Left out at 2k: Legacy.",
    });
  });

  it("leaves out the sentence of a cause that left nothing out", () => {
    expect(leftOutSummary([], ["Legacy"], 8000).detail).toBe("Left out at 8k: Legacy.");
    expect(leftOutSummary(["See also"], [], 8000).detail).toBe(
      "No prose, so left out (lists and tables are not extracted): See also.",
    );
    expect(leftOutSummary([], [], 8000)).toEqual({ count: 0, detail: "" });
  });
});
