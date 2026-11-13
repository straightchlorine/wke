import { describe, expect, it } from "vitest";
import { fitToFrame, type FitItem } from "./frameFit";

const item = (x: number, y: number, clear = 10): FitItem => ({
  x,
  y,
  left: clear,
  right: clear,
  top: clear,
  bottom: clear,
});

describe("fitToFrame", () => {
  it("scales one factor for both axes and centres the marks", () => {
    const items = [item(0, 0), item(100, 50)];
    const { scale, tx, ty } = fitToFrame(items, 220, 400);
    // At scale 2 the 100px spread is 200px wide. Adding 10px of clearance on each side makes 220px, the frame width.
    expect(scale).toBeCloseTo(2, 5);
    const xs = items.map((i) => i.x * scale + tx);
    const ys = items.map((i) => i.y * scale + ty);
    expect(Math.min(...xs) - 10).toBeCloseTo(0, 5);
    expect(220 - (Math.max(...xs) + 10)).toBeCloseTo(0, 5);
    expect(Math.min(...ys) - 10).toBeCloseTo(400 - (Math.max(...ys) + 10), 5);
  });

  it.each([
    ["the width is the tighter axis", { dx: 100, dy: 50 }, { width: 170, height: 400 }, 1.5],
    ["the scale is not a dyadic fraction", { dx: 100, dy: 50 }, { width: 187, height: 400 }, 1.67],
    ["the height is the tighter axis", { dx: 50, dy: 100 }, { width: 400, height: 170 }, 1.5],
    ["a small layout in a big frame", { dx: 10, dy: 10 }, { width: 1000, height: 1000 }, 2],
  ])("picks the largest scale that fits both axes when %s", (_name, spread, frame, expected) => {
    const { scale } = fitToFrame(
      [item(0, 0), item(spread.dx, spread.dy)],
      frame.width,
      frame.height,
    );
    expect(scale).toBeCloseTo(expected, 5);
  });

  it("shrinks a layout that is larger than the frame, never past the clearances", () => {
    const items = [item(0, 0), item(1000, 10), item(500, 800)];
    const { scale, tx, ty } = fitToFrame(items, 300, 300);
    expect(scale).toBeLessThan(0.4);
    for (const i of items) {
      expect(i.x * scale + tx).toBeGreaterThanOrEqual(10 - 1e-6);
      expect(i.x * scale + tx).toBeLessThanOrEqual(290 + 1e-6);
      expect(i.y * scale + ty).toBeGreaterThanOrEqual(10 - 1e-6);
      expect(i.y * scale + ty).toBeLessThanOrEqual(290 + 1e-6);
    }
  });

  it("honours a larger clearance on one side of one mark", () => {
    const wide: FitItem = { x: 0, y: 0, left: 40, right: 10, top: 10, bottom: 10 };
    const { scale, tx } = fitToFrame([wide, item(100, 0)], 200, 200);
    expect(wide.x * scale + tx).toBeGreaterThanOrEqual(40 - 1e-6);
  });

  it("returns the identity for no marks", () => {
    expect(fitToFrame([], 100, 100)).toEqual({ scale: 1, tx: 0, ty: 0 });
  });
});
