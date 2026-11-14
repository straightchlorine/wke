import { describe, expect, it } from "vitest";
import { NOTE_GAP_PX, stackNotes } from "./stackNotes";

describe("stackNotes", () => {
  it("leaves notes that already have room where they want to be", () => {
    expect(stackNotes([0, 200, 400], [80, 80, 80], 1000)).toEqual([0, 200, 400]);
  });

  it("starts each note at least the gap below the previous one", () => {
    const placed = stackNotes([100, 100, 110, 400], [80, 60, 70, 50], 2000);
    expect(placed).toEqual([
      100,
      100 + 80 + NOTE_GAP_PX,
      100 + 80 + NOTE_GAP_PX + 60 + NOTE_GAP_PX,
      400,
    ]);
  });

  it("pulls the last note back inside the article when there is room", () => {
    expect(stackNotes([0, 480], [50, 60], 500)).toEqual([0, 440]);
  });

  it("never lets the last note overlap the one above it", () => {
    const placed = stackNotes([0, 90], [80, 60], 100);
    expect(placed[1]).toBe(80 + NOTE_GAP_PX);
  });

  it("pulls a lone note taller than the article up to the top, not above it", () => {
    expect(stackNotes([10], [200], 100)).toEqual([0]);
  });

  it("handles an empty list", () => {
    expect(stackNotes([], [], 100)).toEqual([]);
  });
});
