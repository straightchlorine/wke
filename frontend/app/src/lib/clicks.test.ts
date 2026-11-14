import { describe, expect, it } from "vitest";
import { isPlainLeftClick } from "./clicks";

const PLAIN = { button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false };

describe("isPlainLeftClick", () => {
  it("accepts a left click with no modifier", () => {
    expect(isPlainLeftClick(PLAIN)).toBe(true);
  });

  it.each([
    ["middle button", { button: 1 }],
    ["right button", { button: 2 }],
    ["meta key", { metaKey: true }],
    ["ctrl key", { ctrlKey: true }],
    ["shift key", { shiftKey: true }],
    ["alt key", { altKey: true }],
  ])("rejects a click with the %s", (_name, change) => {
    expect(isPlainLeftClick({ ...PLAIN, ...change })).toBe(false);
  });
});
