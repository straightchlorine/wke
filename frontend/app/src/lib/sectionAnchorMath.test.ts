import { describe, expect, it } from "vitest";
import { LANDING_GAP_PX, pickAnchorIndex, restoredOffset } from "./sectionAnchorMath";

describe("pickAnchorIndex", () => {
  it("takes the last heading at or above the landing line", () => {
    expect(pickAnchorIndex([-900, -300, 40, 700], 72)).toBe(2);
  });

  it("counts a heading that landed on the line, within rounding", () => {
    expect(pickAnchorIndex([-400, 73, 800], 72)).toBe(1);
  });

  it("falls back to the first heading when all are below the line", () => {
    expect(pickAnchorIndex([300, 900], 72)).toBe(0);
  });

  it("returns -1 without headings", () => {
    expect(pickAnchorIndex([], 72)).toBe(-1);
  });
});

describe("restoredOffset", () => {
  const landing = 56 + LANDING_GAP_PX;

  it("keeps an offset at or below the landing line", () => {
    expect(restoredOffset(300, landing, 1000)).toBe(300);
  });

  it("keeps the depth into a section that is still long enough", () => {
    expect(restoredOffset(-200, landing, 1500)).toBe(-200);
  });

  it("lands the heading at the landing line when the section shrank below the saved depth", () => {
    expect(restoredOffset(-800, landing, 400)).toBe(landing);
  });

  it("keeps a depth that leaves one line of the section below the landing line", () => {
    expect(restoredOffset(-300, landing, 400)).toBe(-300);
  });

  it("lands the heading when the section leaves less than one line below the landing line", () => {
    expect(restoredOffset(-300, landing, 380)).toBe(landing);
  });

  it("lands the heading when the section is shorter than one line", () => {
    expect(restoredOffset(-800, landing, 20)).toBe(landing);
  });
});
