import { describe, expect, it } from "vitest";
import { nextRovingIndex } from "./rovingIndex";

describe("nextRovingIndex", () => {
  it.each([
    ["ArrowRight", 1, 2],
    ["ArrowDown", 1, 2],
    ["ArrowLeft", 1, 0],
    ["ArrowUp", 1, 0],
    ["Home", 3, 0],
    ["End", 1, 3],
  ])("%s from item %i focuses item %i of 4", (key, current, expected) => {
    expect(nextRovingIndex(key, current, 4)).toBe(expected);
  });

  it.each([
    ["ArrowRight", 3, 3],
    ["ArrowDown", 3, 3],
    ["ArrowLeft", 0, 0],
    ["ArrowUp", 0, 0],
  ])("%s at the end of the row stays on item %i", (key, current, expected) => {
    expect(nextRovingIndex(key, current, 4)).toBe(expected);
  });

  it("returns null for a key that moves nothing", () => {
    expect(nextRovingIndex("Enter", 1, 4)).toBeNull();
    expect(nextRovingIndex("a", 1, 4)).toBeNull();
  });
});
