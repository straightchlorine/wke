import { describe, expect, it } from "vitest";
import { guaranteedNameIds, plateLayoutOptions, type PlateFrame } from "./plateLayoutOptions";
import { legendRect } from "./plateLegend";

const BASE: PlateFrame = {
  variant: "index",
  width: 709,
  height: 709,
  chipOverlaysFrame: true,
  underDesktop: false,
};

const CHIP = { id: -1, y: 0, width: 204, height: 30, text: "" };

describe("plateLayoutOptions label options", () => {
  it.each([
    {
      name: "an index graph on a phone viewport",
      frame: { ...BASE, width: 348, height: 348, chipOverlaysFrame: false, underDesktop: true },
      expected: { phone: true, desktop: false, minVisibleChars: 18, reserved: [] },
    },
    {
      name: "an index graph on a tablet viewport",
      frame: { ...BASE, width: 531, height: 531, underDesktop: true },
      expected: {
        phone: false,
        desktop: false,
        minVisibleChars: 18,
        reserved: [{ ...CHIP, x: 327 }],
      },
    },
    {
      name: "an index graph on a desktop viewport",
      frame: { ...BASE, width: 1064, height: 1064 },
      expected: {
        phone: false,
        desktop: true,
        minVisibleChars: undefined,
        reserved: [{ ...CHIP, x: 860 }],
      },
    },
    {
      name: "an index graph whose caller says it is compact on a wide viewport",
      frame: { ...BASE, compact: true },
      expected: {
        phone: true,
        desktop: false,
        minVisibleChars: undefined,
        reserved: [{ ...CHIP, x: 505 }],
      },
    },
    {
      name: "an index graph whose caller says it is not compact on a phone viewport",
      frame: { ...BASE, compact: false, chipOverlaysFrame: false, underDesktop: true },
      expected: { phone: false, desktop: false, minVisibleChars: 18, reserved: [] },
    },
    {
      name: "a related graph drawn for a phone",
      frame: { ...BASE, variant: "related" as const, width: 300, height: 300, compact: true },
      expected: { phone: true, desktop: true, minVisibleChars: 18, reserved: [] },
    },
    {
      name: "a related graph beside the stats chip",
      frame: { ...BASE, variant: "related" as const, width: 364, height: 364, compact: false },
      expected: {
        phone: false,
        desktop: true,
        minVisibleChars: 18,
        reserved: [{ ...CHIP, x: 160 }],
      },
    },
    {
      name: "a related graph in a frame just wide enough for names on leaders",
      frame: { ...BASE, variant: "related" as const, width: 270, height: 270, compact: true },
      expected: { phone: true, desktop: true, minVisibleChars: 18, reserved: [] },
    },
    {
      name: "a related graph in a frame just too small for names on leaders",
      frame: { ...BASE, variant: "related" as const, width: 269, height: 269, compact: true },
      expected: { phone: true, desktop: false, minVisibleChars: 18, reserved: [] },
    },
    {
      name: "a related graph in a frame under the phone width, with no word from the caller",
      frame: { ...BASE, variant: "related" as const, width: 600, height: 600 },
      expected: { phone: true, desktop: true, minVisibleChars: 18, reserved: [] },
    },
    {
      name: "a related graph in a frame over the phone width, with no word from the caller",
      frame: { ...BASE, variant: "related" as const, width: 800, height: 800 },
      expected: {
        phone: false,
        desktop: true,
        minVisibleChars: 18,
        reserved: [{ ...CHIP, x: 596 }],
      },
    },
  ])("sets $name", ({ frame, expected }) => {
    const { labels } = plateLayoutOptions(frame);
    expect(labels).toMatchObject({
      variant: frame.variant,
      phone: expected.phone,
      desktop: expected.desktop,
      minVisibleChars: expected.minVisibleChars,
      width: frame.width,
      height: frame.height,
    });
    expect(labels.reservedBoxes).toEqual(expected.reserved);
  });

  it("shrinks the stats chip's box to a frame narrower than the chip", () => {
    const { labels } = plateLayoutOptions({ ...BASE, width: 150, height: 150 });
    expect(labels.reservedBoxes).toEqual([{ ...CHIP, x: 0, width: 150 }]);
  });
});

describe("plateLayoutOptions legend", () => {
  const legend = { width: 146, height: 22 };
  const rect = legendRect(legend, 709);

  it("keeps dots and outlines off the legend chip and names three px clear of it", () => {
    const { layout, labels } = plateLayoutOptions({ ...BASE, legendSize: legend });
    expect(layout.excludeBoxes).toEqual([
      { ...CHIP, x: 505 },
      { ...rect, hull: true },
    ]);
    expect(labels.reservedBoxes).toEqual([
      { ...CHIP, x: 505 },
      {
        id: -2,
        x: rect.x - 3,
        y: rect.y - 3,
        width: rect.width + 6,
        height: rect.height + 6,
        text: "",
      },
    ]);
  });

  it("ignores the legend chip on the related graph", () => {
    const { layout, labels } = plateLayoutOptions({
      ...BASE,
      variant: "related",
      compact: true,
      legendSize: legend,
    });
    expect(layout.excludeBoxes).toEqual([]);
    expect(labels.reservedBoxes).toEqual([]);
  });
});

describe("plateLayoutOptions layout options", () => {
  it.each([
    { width: 348, height: 348, squareFrame: undefined, square: true },
    { width: 479, height: 479, squareFrame: undefined, square: true },
    { width: 480, height: 480, squareFrame: undefined, square: false },
    { width: 348, height: 400, squareFrame: undefined, square: false },
    { width: 348, height: 348, squareFrame: false, square: false },
    { width: 709, height: 709, squareFrame: true, square: true },
  ])(
    "treats a $width x $height frame with squareFrame $squareFrame as square: $square",
    ({ width, height, squareFrame, square }) => {
      const { layout } = plateLayoutOptions({ ...BASE, width, height, squareFrame });
      expect(layout.squareFrame).toBe(square);
      expect(layout.radiusRange).toEqual(square ? [4, 11] : [5, 16]);
    },
  );

  it.each([
    { variant: "index" as const, wallMargin: 12.5 },
    { variant: "related" as const, wallMargin: undefined },
  ])(
    "sets wall margin $wallMargin and the outline padding on the $variant graph",
    ({ variant, wallMargin }) => {
      const { layout } = plateLayoutOptions({ ...BASE, variant, compact: true });
      expect(layout).toMatchObject({ width: 709, height: 709, hullPad: 18, wallMargin });
    },
  );
});

describe("plateLayoutOptions name length", () => {
  it.each([
    { name: "an index graph on a phone", frame: { ...BASE, chipOverlaysFrame: false }, chars: 18 },
    { name: "an index graph on a wider viewport", frame: BASE, chars: 26 },
    {
      name: "a related graph",
      frame: { ...BASE, variant: "related" as const, compact: true },
      chars: 26,
    },
  ])("is $chars characters on $name", ({ frame, chars }) => {
    expect(plateLayoutOptions(frame).nameChars).toBe(chars);
  });
});

describe("guaranteedNameIds", () => {
  const nodes = [{ id: 7, role: "related" as const }, { id: 8, role: "seed" as const }, { id: 9 }];

  it.each([
    { name: "the first node on the index graph", variant: "index" as const, list: nodes, ids: [7] },
    { name: "the seed on the related graph", variant: "related" as const, list: nodes, ids: [8] },
    { name: "nothing on an empty index graph", variant: "index" as const, list: [], ids: [] },
    {
      name: "nothing on a related graph with no seed",
      variant: "related" as const,
      list: [{ id: 1 }],
      ids: [],
    },
  ])("is $name", ({ variant, list, ids }) => {
    expect([...guaranteedNameIds(variant, list)]).toEqual(ids);
  });
});
