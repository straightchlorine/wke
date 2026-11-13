import { describe, expect, it } from "vitest";
import { GLYPH_LEFT_PX, LABEL_HALO_PAD, LABEL_LINE_HEIGHT, boxWidthFor } from "./labelGeometry";
import type { LabelBox } from "./labelGeometry";
import { nameBackingRect, nameLeft, textBaselineY, textOriginX } from "./labelText";

// Text 80px wide: the box adds what `boxWidthFor` adds to a text of no width.
const TEXT_WIDTH = 80;
const box: LabelBox = {
  id: 1,
  x: 100,
  y: 50,
  width: boxWidthFor(TEXT_WIDTH),
  height: 20,
  text: "Lizzie Borden",
};

describe("textOriginX", () => {
  it("starts the text a glyph offset in from the box's left edge", () => {
    expect(textOriginX(box)).toBe(100 + GLYPH_LEFT_PX);
  });

  it("uses the box's own text origin when it has one", () => {
    expect(textOriginX({ ...box, textX: 190 })).toBe(190);
    expect(textOriginX({ ...box, textX: 0 })).toBe(0);
  });
});

describe("textBaselineY", () => {
  it("puts a one-line baseline one halo pad above the box's bottom edge", () => {
    expect(textBaselineY(box)).toBe(50 + 20 - LABEL_HALO_PAD);
  });

  it("lifts a two-line name by one line so its second line lands on that baseline", () => {
    const two = {
      ...box,
      height: 20 + LABEL_LINE_HEIGHT,
      lines: ["A b", "c d"] as [string, string],
    };
    expect(textBaselineY(two)).toBe(
      50 + 20 + LABEL_LINE_HEIGHT - LABEL_HALO_PAD - LABEL_LINE_HEIGHT,
    );
  });
});

describe("nameLeft", () => {
  it.each([
    ["start", undefined, 100 + GLYPH_LEFT_PX],
    ["start", 120, 120],
    ["end", 190, 190 - TEXT_WIDTH],
    ["middle", 145, 145 - TEXT_WIDTH / 2],
  ] as const)(
    "is the left end of the glyphs for a %s anchor at textX %s",
    (textAnchor, textX, left) => {
      expect(nameLeft({ ...box, textAnchor, textX })).toBe(left);
    },
  );
});

describe("nameBackingRect", () => {
  it("reaches past the glyphs on both sides and sits just inside the box vertically", () => {
    expect(nameBackingRect({ ...box, textAnchor: "start" })).toEqual({
      x: 100 + GLYPH_LEFT_PX - 3,
      y: 54,
      width: TEXT_WIDTH + 6,
      height: 18,
    });
  });

  it("follows the anchored end of the text", () => {
    const rect = nameBackingRect({ ...box, textAnchor: "end", textX: 190 });
    expect(rect.x).toBe(190 - TEXT_WIDTH - 3);
    expect(rect.width).toBe(TEXT_WIDTH + 6);
  });
});
