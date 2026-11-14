import { describe, expect, it } from "vitest";
import type { DossierListItem } from "../api/generated";
import { DOSSIERS_LIST_LIMIT } from "../api/queries";
import { copyAsContextMessage, storedDossiersCounter, topDossierTip } from "./counters";

const item = { rev_id: 123 };

describe("storedDossiersCounter", () => {
  const items: DossierListItem[] = [1, 2, 3].map((n) => ({
    page_id: n,
    title: `T${n}`,
    rev_id: n,
    pinned_at: "2026-11-01T00:00:00Z",
    freshness_state: "fresh",
    edits_since_pin: 0,
    largest_budget_filled: 8000,
    sections: 1,
    built_at: "2026-11-01T00:00:00Z",
  }));
  it.each([
    ["a complete list", { items, next_cursor: null }, false, "3", true],
    ["a list with more pages", { items, next_cursor: "c" }, false, `${DOSSIERS_LIST_LIMIT}+`, true],
    ["a list kept after a later failure", { items, next_cursor: null }, true, "3", true],
    ["loading", undefined, false, "...", false],
    ["a failed request", undefined, true, "unknown", false],
  ])("%s", (_name, list, failed, label, known) => {
    expect(storedDossiersCounter(list, failed)).toEqual({ label, known });
  });
});

describe("topDossierTip", () => {
  it.each([
    [
      "tokens known",
      { used_est_tokens: 7500, requested: 8000 },
      false,
      "Revision 123, 7,500 of 8,000 tokens",
    ],
    ["tokens pending", undefined, false, "Revision 123, tokens pending"],
    ["tokens failed", undefined, true, "Revision 123"],
  ] as const)("%s", (_name, used, failed, expected) => {
    expect(topDossierTip(item, used, failed)).toBe(expected);
  });
});

describe("copyAsContextMessage", () => {
  it.each([
    [
      "both known",
      { used_est_tokens: 1234 },
      item,
      "Copied as markdown, 1,234 dossier tokens, revision 123",
    ],
    ["no token count", undefined, item, "Copied as context"],
    ["no stored entry", { used_est_tokens: 1234 }, undefined, "Copied as context"],
  ])("%s", (_name, used, entry, expected) => {
    expect(copyAsContextMessage(used, entry)).toBe(expected);
  });
});
