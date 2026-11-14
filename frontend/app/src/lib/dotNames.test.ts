import { describe, expect, it } from "vitest";
import { dotNamesFor } from "./dotNames";
import type { LaidOutNode } from "./graphLayout";
import { boxesOverlap, type LabelBox } from "./labelGeometry";

const FRAME = { width: 400, height: 400 };

function dot(id: number, x: number, y: number, title = `Dot ${id}`): LaidOutNode {
  return { id, title, views: 1, x, y, radius: 6, cluster: 0 };
}

function label(id: number): LabelBox {
  return { id, x: 0, y: 0, width: 10, height: 10, text: "" };
}

const nodes = [dot(1, 100, 100), dot(2, 300, 300), dot(3, 200, 50)];

function names(ids: Array<number | null>, over: Partial<Parameters<typeof dotNamesFor>[1]> = {}) {
  return dotNamesFor(ids, {
    variant: "index",
    selectedId: null,
    nodes,
    labelPlacements: new Map(),
    reservedBoxes: [],
    ...FRAME,
    ellipsisChars: 26,
    ...over,
  });
}

describe("dotNamesFor", () => {
  it("names a dot that has no permanent label, beside its own dot", () => {
    const result = names([1]);
    const { box, backed } = result.get(1)!;
    expect(backed).toBe(false);
    expect(box.id).toBe(1);
    expect(box.text).toBe("Dot 1");
  });

  it("gives no second name to a dot that already has a label", () => {
    const result = names([1, 2], {
      labelPlacements: new Map([
        [1, label(1)],
        [2, null],
      ]),
    });
    expect([...result.keys()]).toEqual([2]);
  });

  it("moves the selected dot's name of the related graph beside the dot, on a backing", () => {
    const placements = new Map([[1, label(1)]]);
    const related = names([1], { variant: "related", selectedId: 1, labelPlacements: placements });
    expect(related.get(1)?.backed).toBe(true);
    const index = names([1], { variant: "index", selectedId: 1, labelPlacements: placements });
    expect(index.size).toBe(0);
  });

  it("names only the selected dot of the related graph, since every other dot keeps its label", () => {
    const placements = new Map([
      [1, label(1)],
      [2, label(2)],
    ]);
    const result = names([1, 2], {
      variant: "related",
      selectedId: 1,
      labelPlacements: placements,
    });
    expect([...result.keys()]).toEqual([1]);
  });

  it("places a name on the side away from the middle of a frame that is not square", () => {
    const wide = { width: 600, height: 300 };
    const blocker = { ...label(-1), x: 0, y: 150, width: 170, height: 100 };
    // Left of the dot is blocked, so the name takes the side away from the middle vertically.
    const low = names([1], { ...wide, nodes: [dot(1, 200, 200)], reservedBoxes: [blocker] }).get(
      1,
    )!;
    expect(low.box.y).toBeGreaterThan(200);
    // The first choice is left of a dot in the left half of the frame, however tall the frame is.
    const left = names([1], { ...wide, nodes: [dot(1, 200, 100)] }).get(1)!;
    expect(left.box.x + left.box.width).toBeLessThanOrEqual(200);
  });

  it("names each dot once and skips null and unknown ids", () => {
    const result = names([null, 2, 99, 2, 1]);
    expect([...result.keys()]).toEqual([2, 1]);
  });

  it("keeps a name off the permanent labels and the reserved boxes", () => {
    const placed = { ...label(5), x: 40, y: 90, width: 56, height: 20 };
    const reserved = { ...label(-1), x: 100, y: 60, width: 60, height: 30 };
    const { box } = names([1], {
      labelPlacements: new Map([[5, placed]]),
      reservedBoxes: [reserved],
    }).get(1)!;
    expect(boxesOverlap(box, placed)).toBe(false);
    expect(boxesOverlap(box, reserved)).toBe(false);
  });

  it("cuts a long title to the character limit and keeps the whole title for the tooltip", () => {
    const long = [dot(1, 100, 100, "A very long article title that runs on")];
    const { box } = names([1], { nodes: long, ellipsisChars: 12 }).get(1)!;
    expect(box.text.length).toBeLessThanOrEqual(12);
    expect(box.text.endsWith("...")).toBe(true);
    expect(box.fullText).toBe("A very long article title that runs on");
  });
});
