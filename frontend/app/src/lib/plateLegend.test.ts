import { describe, expect, it } from "vitest";
import { legendChipSize, legendRect, LEGEND_INSET_PX, PLATE_EDGE_PX } from "./plateLegend";

describe("legendChipSize", () => {
  it.each([
    // 2 borders, 2 x 6 padding, 6 swatches of 12, 5 gaps of 12.
    ["a fine pointer", 6, false, { width: 2 + 12 + 72 + 60, height: 22 }],
    // 2 borders, 2 x 8 padding, 6 swatches of 12, 5 gaps of 32 (a 44px pitch).
    ["a coarse pointer", 6, true, { width: 2 + 16 + 72 + 5 * 32, height: 28 }],
    ["a single swatch, with no gap to count", 1, false, { width: 2 + 12 + 12, height: 22 }],
    ["no swatches, which has no gap to count either", 0, false, { width: 2 + 12, height: 22 }],
  ])("measures the chip for %s", (_name, count, coarse, expected) => {
    expect(legendChipSize(count, coarse)).toEqual(expected);
  });
});

describe("legendRect", () => {
  it("sits at the frame's corner inset, measured in the drawing area", () => {
    const rect = legendRect({ width: 146, height: 22 }, 600);
    const inset = LEGEND_INSET_PX - PLATE_EDGE_PX;
    expect(rect).toEqual({ x: inset, y: 600 - inset - 22, width: 146, height: 22 });
  });
});
