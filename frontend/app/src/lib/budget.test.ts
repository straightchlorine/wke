import { describe, expect, it } from "vitest";
import {
  BUDGET_OPTIONS,
  budgetAlias,
  budgetToSegmentValue,
  dossierBudgetHelp,
  homeBudgetHelp,
  parseBudget,
} from "./budget";

describe("parseBudget", () => {
  it.each([
    ["8k", 8000],
    ["32K", 32000],
    ["2k", 2000],
    ["32k", 32000],
    ["32000", 32000],
    ["2000", 2000],
    [32000, 32000],
    ["junk", 8000],
    ["16000", 8000],
    ["", 8000],
    [undefined, 8000],
    [null, 8000],
    [4000, 8000],
  ])("parses %j as %i", (raw, expected) => {
    expect(parseBudget(raw)).toBe(expected);
  });

  it("round-trips every budget through its alias", () => {
    for (const budget of [2000, 8000, 32000] as const) {
      expect(parseBudget(budgetAlias(budget))).toBe(budget);
      expect(parseBudget(budgetToSegmentValue(budget))).toBe(budget);
    }
  });
});

describe("BUDGET_OPTIONS", () => {
  it("lists every budget in order with its alias as the label", () => {
    expect(BUDGET_OPTIONS).toEqual([
      { value: "2000", label: "2k" },
      { value: "8000", label: "8k" },
      { value: "32000", label: "32k" },
    ]);
  });
});

describe("budget help text", () => {
  it("drops the keys sentence on a coarse pointer", () => {
    expect(dossierBudgetHelp("chars/4", true)).not.toMatch(/Keys/);
    expect(dossierBudgetHelp("chars/4", false)).toMatch(/Keys 1, 2, 3 pick 2k, 8k, 32k\.$/);
    expect(dossierBudgetHelp("chars/4", true)).toContain("Estimated with chars/4");
    expect(homeBudgetHelp(true)).not.toMatch(/Keys/);
    expect(homeBudgetHelp(true)).toMatch(/2k, 8k or 32k/);
    expect(homeBudgetHelp(false)).toMatch(/^Keys 1, 2, 3/);
  });
});
