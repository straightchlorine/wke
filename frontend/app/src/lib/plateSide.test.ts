import { describe, expect, it } from "vitest";
import { plateSide } from "./plateSide";

describe("plateSide", () => {
  it("is the column's width, in whole px, when the window has room for the frame and its board", () => {
    expect(plateSide(614, 2000)).toBe(614);
    expect(plateSide(614.7, 2000)).toBe(614);
  });

  it("is what the window leaves once the gap, the board and the clearance are counted", () => {
    // 500 - 8 (gap) - 154 (board) - 12 (clearance).
    expect(plateSide(900, 500)).toBe(326);
  });

  it("never goes under the least side, however short the window", () => {
    expect(plateSide(900, 100)).toBe(320);
  });

  it("holds to the on-screen cap under the root zoom", () => {
    // At zoom 1.75 a 750px column would draw 1313px wide; the cap leaves 1000 / 1.75.
    expect(plateSide(750, 5000, 1.75)).toBe(571);
    expect(571 * 1.75).toBeLessThanOrEqual(1000);
  });

  it("follows the column where it is narrower than the on-screen cap", () => {
    expect(plateSide(640, 5000, 1.25)).toBe(640);
  });
});
