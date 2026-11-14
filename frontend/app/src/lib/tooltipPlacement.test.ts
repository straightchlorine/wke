import { describe, expect, it } from "vitest";
import {
  AVOID_WEIGHT,
  OUTLINE_POINT_COST,
  bridgeBox,
  candidateSpots,
  chooseClearSpot,
  overlapCost,
  placeByTrigger,
  placeUnderFrame,
  scrollKeepsFrame,
  type PlacementLimits,
  type Rect,
  type TipClearance,
} from "./tooltipPlacement";

const rect = (left: number, top: number, right: number, bottom: number): Rect => ({
  left,
  top,
  right,
  bottom,
});

const LIMITS: PlacementLimits = {
  minLeft: 16,
  maxRight: 1008,
  viewportHeight: 768,
  inset: 16,
  gap: 6,
  zoom: 1,
};

const TIP = { width: 200, height: 100 };

function clearance(overrides: Partial<TipClearance> = {}): TipClearance {
  return {
    anchor: rect(100, 300, 400, 340),
    frame: rect(50, 250, 950, 600),
    avoid: [],
    points: [],
    ...overrides,
  };
}

describe("placeByTrigger", () => {
  it("puts the tooltip above the trigger by default", () => {
    const placed = placeByTrigger(rect(100, 400, 120, 414), TIP, LIMITS);
    expect(placed).toEqual({ x: 100, y: 400 - 6 - 100, maxHeight: null });
  });

  it.each([
    [100, 16],
    [101, 136 + 6],
  ])("with exactly 100 px above the trigger, a %i px tooltip goes to y %i", (height, y) => {
    const placed = placeByTrigger(rect(100, 122, 120, 136), { width: 200, height }, LIMITS);
    expect(placed).toEqual({ x: 100, y, maxHeight: null });
  });

  it("goes below when above would clip and below fits", () => {
    const placed = placeByTrigger(rect(100, 50, 120, 64), TIP, LIMITS);
    expect(placed).toEqual({ x: 100, y: 64 + 6, maxHeight: null });
  });

  it.each([
    ["below when below is roomier", rect(100, 200, 120, 214), 214 + 6, 532],
    ["above when above is roomier", rect(100, 560, 120, 574), 16, 538],
  ])("limits a tall tooltip to the roomier side: %s", (_name, button, y, maxHeight) => {
    const placed = placeByTrigger(button, { width: 200, height: 700 }, LIMITS);
    expect(placed).toEqual({ x: 100, y, maxHeight });
  });

  it("never gives a negative max height", () => {
    const placed = placeByTrigger(rect(100, 10, 120, 760), TIP, LIMITS);
    expect(placed.maxHeight).toBe(0);
  });

  it.each([
    [5, 16],
    [990, 1008 - 200],
  ])("keeps the tooltip inside the horizontal limits: left %i gives x %i", (left, x) => {
    const placed = placeByTrigger(rect(left, 400, left + 20, 414), TIP, LIMITS);
    expect(placed.x).toBe(x);
  });
});

describe("overlapCost", () => {
  const spot = { x: 300, y: 200 };

  it("counts the covered area of a region", () => {
    expect(overlapCost(spot, TIP, clearance({ others: [rect(400, 250, 900, 900)] }))).toBe(
      100 * 50,
    );
  });

  it("counts a region to avoid AVOID_WEIGHT times more than one of the others", () => {
    const region = rect(400, 250, 900, 900);
    const avoided = overlapCost(spot, TIP, clearance({ avoid: [region] }));
    const other = overlapCost(spot, TIP, clearance({ others: [region] }));
    expect(avoided).toBe(other * AVOID_WEIGHT);
  });

  it("charges OUTLINE_POINT_COST for each outline point inside the tooltip", () => {
    const inside = { x: 350, y: 250 };
    const outside = { x: 700, y: 250 };
    expect(overlapCost(spot, TIP, clearance({ otherPoints: [inside, inside, outside] }))).toBe(
      2 * OUTLINE_POINT_COST,
    );
    expect(overlapCost(spot, TIP, clearance({ points: [inside] }))).toBe(
      OUTLINE_POINT_COST * AVOID_WEIGHT,
    );
  });

  it("counts an outline point inside the tooltip as 100 px^2", () => {
    const point = { x: 350, y: 250 };
    const region = rect(300, 200, 310, 210);
    expect(overlapCost(spot, TIP, clearance({ otherPoints: [point] }))).toBe(
      overlapCost(spot, TIP, clearance({ others: [region] })),
    );
  });

  it("is zero when nothing is covered", () => {
    expect(overlapCost(spot, TIP, clearance({ avoid: [rect(0, 0, 100, 100)] }))).toBe(0);
  });
});

describe("candidateSpots", () => {
  const trigger = { x: 300, y: 200 };

  it("lists the trigger spot, the anchor sides, then the frame corners", () => {
    expect(candidateSpots(trigger, TIP, clearance(), LIMITS)).toEqual([
      { x: 300, y: 200, far: false },
      { x: 406, y: 240, far: true },
      { x: 406, y: 200, far: true },
      { x: 300, y: 346, far: false },
      { x: 406, y: 270, far: true },
      { x: 200, y: 194, far: true },
      { x: 742, y: 258, far: true },
      { x: 742, y: 492, far: true },
    ]);
  });

  it("moves the spot beside the anchor to the front for besideFirst", () => {
    const spots = candidateSpots(trigger, TIP, clearance({ besideFirst: true }), LIMITS);
    expect(spots).toHaveLength(8);
    expect(spots[0]).toEqual({ x: 406, y: 270, far: true });
    expect(spots[1]).toEqual({ x: 300, y: 200, far: false });
  });

  it("drops spots that leave the horizontal limits", () => {
    const spots = candidateSpots(trigger, TIP, clearance(), { ...LIMITS, maxRight: 520 });
    expect(spots.map((spot) => spot.x)).toEqual([300, 300, 200]);
  });

  it("drops spots too close to the top or bottom of the viewport", () => {
    const spots = candidateSpots({ x: 300, y: 5 }, TIP, clearance(), LIMITS);
    expect(spots.some((spot) => spot.y < 16)).toBe(false);
    expect(spots[0]).toEqual({ x: 406, y: 240, far: true });
    const low = candidateSpots({ x: 300, y: 660 }, TIP, clearance(), LIMITS);
    expect(low.some((spot) => spot.y + TIP.height > 768 - 16)).toBe(false);
  });
});

describe("chooseClearSpot", () => {
  const trigger = { x: 300, y: 200 };

  it("takes the trigger spot when it is clear", () => {
    const choice = chooseClearSpot(trigger, TIP, clearance(), LIMITS);
    expect(choice).toEqual({ spot: { x: 300, y: 200, far: false }, overlap: 0 });
  });

  it("takes the first later spot that is clear", () => {
    const choice = chooseClearSpot(
      trigger,
      TIP,
      clearance({ avoid: [rect(300, 200, 500, 300)] }),
      LIMITS,
    );
    expect(choice).toEqual({ spot: { x: 300, y: 346, far: false }, overlap: 0 });
  });

  it("falls through to the last frame corner when everything before it is covered", () => {
    const choice = chooseClearSpot(
      trigger,
      TIP,
      clearance({ avoid: [rect(0, 0, 1024, 450)] }),
      LIMITS,
    );
    expect(choice.spot).toEqual({ x: 742, y: 492, far: true });
    expect(choice.overlap).toBe(0);
  });

  it("takes the spot covering the least when none is clear", () => {
    const narrow = { ...LIMITS, maxRight: 520 };
    const choice = chooseClearSpot(
      trigger,
      TIP,
      clearance({ avoid: [rect(250, 0, 1000, 400)] }),
      narrow,
    );
    expect(choice.spot).toEqual({ x: 300, y: 346, far: false });
    expect(choice.overlap).toBe(200 * 54 * AVOID_WEIGHT);
  });

  it("keeps the earlier spot on a tie", () => {
    const choice = chooseClearSpot(
      trigger,
      TIP,
      clearance({ avoid: [rect(0, 0, 1024, 768)] }),
      LIMITS,
    );
    expect(choice.spot).toEqual({ x: 300, y: 200, far: false });
  });

  it("prefers covering 500 px^2 of the others over 1 px^2 of an avoided region", () => {
    const choice = chooseClearSpot(
      trigger,
      TIP,
      clearance({
        avoid: [rect(499, 299, 520, 301)],
        others: [rect(300, 346, 350, 356)],
      }),
      { ...LIMITS, minLeft: 250, maxRight: 520 },
    );
    expect(choice).toEqual({ spot: { x: 300, y: 346, far: false }, overlap: 500 });
  });

  it("returns no spot when no candidate fits", () => {
    const choice = chooseClearSpot(trigger, TIP, clearance(), { ...LIMITS, maxRight: 100 });
    expect(choice).toEqual({ spot: null, overlap: Infinity });
  });
});

describe("placeUnderFrame", () => {
  it("places the tooltip just under the frame, left-aligned with the anchor", () => {
    const placed = placeUnderFrame(TIP, clearance({ outside: rect(0, 600, 1024, 800) }), LIMITS);
    expect(placed).toEqual({ spot: { x: 100, y: 606, far: true }, scrollBy: 0 });
  });

  it("asks for the scroll that brings a tooltip below the fold into view", () => {
    const placed = placeUnderFrame(
      TIP,
      clearance({ frame: rect(50, 250, 950, 700), outside: rect(0, 700, 1024, 900) }),
      LIMITS,
    );
    expect(placed?.scrollBy).toBe(706 + 100 - (768 - 16));
  });

  it.each([
    ["without an outside region", clearance(), LIMITS],
    [
      "when it ends below the outside region",
      clearance({ outside: rect(0, 600, 1024, 650) }),
      LIMITS,
    ],
    [
      "when it needs more scrolling than allowed",
      clearance({ frame: rect(50, 250, 950, 900), outside: rect(0, 900, 1024, 2000) }),
      LIMITS,
    ],
    [
      "when it does not fit the width",
      clearance({ outside: rect(0, 600, 1024, 800) }),
      { ...LIMITS, maxRight: 150 },
    ],
  ])("gives up %s", (_name, clear, limits) => {
    expect(placeUnderFrame(TIP, clear, limits)).toBeNull();
  });

  it("scales the allowed scroll by the zoom", () => {
    const clear = clearance({ frame: rect(50, 250, 950, 900), outside: rect(0, 900, 1024, 2000) });
    const zoomed = { ...LIMITS, zoom: 2, inset: 32, gap: 12, viewportHeight: 768 };
    expect(placeUnderFrame(TIP, clear, zoomed)).not.toBeNull();
  });

  it("keeps the spot inside the left limit", () => {
    const placed = placeUnderFrame(
      TIP,
      clearance({ anchor: rect(2, 300, 40, 340), outside: rect(0, 600, 1024, 800) }),
      LIMITS,
    );
    expect(placed?.spot.x).toBe(16);
  });
});

describe("scrollKeepsFrame", () => {
  it.each([
    [54, 54, 100, 1, true],
    [53.6, 54, 100, 1, true],
    [53, 54, 100, 1, false],
    [34, 34, 10, 1, true],
    [35, 35, 10, 1, false],
    [60, 60, 12, 2, true],
    [61, 61, 12, 2, false],
  ])("scrolled %f of %f with the frame at %f, zoom %i: %s", (scrolled, wanted, top, zoom, ok) => {
    expect(scrollKeepsFrame(scrolled, wanted, top, zoom)).toBe(ok);
  });
});

describe("bridgeBox", () => {
  it("spans from the wider of the tooltip and the anchor", () => {
    expect(bridgeBox({ x: 300, y: 400 }, 200, rect(100, 300, 700, 380))).toEqual({
      left: -200,
      width: 600,
      height: 20,
    });
  });

  it("matches the tooltip when the anchor is narrower", () => {
    expect(bridgeBox({ x: 300, y: 400 }, 200, rect(350, 300, 400, 380))).toEqual({
      left: 0,
      width: 200,
      height: 20,
    });
  });
});
