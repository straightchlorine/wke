import { describe, expect, it } from "vitest";
import { buildVerbHint, notBuiltHint, searchButtonLabel } from "./searchButton";

describe("searchButtonLabel", () => {
  it.each([
    ["ready", "Open"],
    ["partial", "Open"],
    ["building", "Open"],
    ["none", "Build"],
    [null, "Build"],
  ] as const)("labels a %s suggestion %s", (state, label) => {
    expect(searchButtonLabel(state)).toBe(label);
  });
});

describe("build hints", () => {
  it.each([
    ["keyboard", "not built yet, Enter builds it", "Enter builds it"],
    ["touch", "not built yet, tap builds it", "tap builds it"],
  ] as const)("on %s", (input, notBuilt, verb) => {
    expect(notBuiltHint(input)).toBe(notBuilt);
    expect(buildVerbHint(input)).toBe(verb);
  });
});
