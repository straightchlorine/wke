import { describe, expect, it } from "vitest";
import { MIN_LABEL_GAP_PX, type RulerLabel, thinLabels, tokenToFraction } from "./rulerLabels";

const label = (key: string, pos: number, kind: RulerLabel["kind"] = "tick"): RulerLabel => ({
  key,
  text: key,
  pos,
  kind,
});

describe("thinLabels", () => {
  it.each([
    ["labels far enough apart", [20, 60, 100], ["a", "b", "c"]],
    [
      "a label exactly the minimum gap from the last one",
      [100, 100 + MIN_LABEL_GAP_PX],
      ["a", "b"],
    ],
    [
      "a label just under the minimum gap from the last one",
      [100, 100 + MIN_LABEL_GAP_PX - 1],
      ["a"],
    ],
    [
      "a run of crowded labels, leaving the first and a distant one",
      [100, 105, 110, 160],
      ["a", "d"],
    ],
  ])("keeps %s", (_name, positions, expected) => {
    const labels = positions.map((pos, i) => label("abcd"[i]!, pos));
    expect(thinLabels(labels, 300).map((l) => l.key)).toEqual(expected);
  });

  it("keeps the first of two crowding labels of one kind in position order, whatever the input order", () => {
    const kept = thinLabels([label("b", 105), label("a", 100)], 300);
    expect(kept.map((l) => l.key)).toEqual(["a"]);
  });

  it("returns the kept labels top to bottom whatever their kind or input order", () => {
    const kept = thinLabels([label("s", 60, "section"), label("t", 20, "tick")], 300);
    expect(kept.map((l) => l.key)).toEqual(["t", "s"]);
  });

  it("keeps the last labelled tick over a crowding earlier tick or section", () => {
    const kept = thinLabels(
      [label("s", 190, "section"), label("t", 196, "tick"), label("last", 198, "end")],
      210,
    );
    expect(kept.map((l) => l.key)).toEqual(["last"]);
  });

  it("clamps labels inside the ruler", () => {
    const kept = thinLabels([label("top", -5), label("bottom", 999)], 100);
    expect(kept.map((l) => l.pos)).toEqual([8, 92]);
  });

  it("shows one label where a section and a tick share a position", () => {
    const kept = thinLabels([label("0", 30, "tick"), label("0s", 30, "section")], 200);
    expect(kept.map((l) => l.key)).toEqual(["0s"]);
  });
});

describe("tokenToFraction", () => {
  const breakpoints = [
    { token: 100, fraction: 0.1 },
    { token: 300, fraction: 0.5 },
    { token: 400, fraction: 1 },
  ];

  it("interpolates linearly between the surrounding breakpoints", () => {
    expect(tokenToFraction(200, breakpoints)).toBeCloseTo(0.3);
    expect(tokenToFraction(350, breakpoints)).toBeCloseTo(0.75);
  });

  it("returns the first fraction at or below the first breakpoint", () => {
    expect(tokenToFraction(0, breakpoints)).toBe(0.1);
    expect(tokenToFraction(100, breakpoints)).toBe(0.1);
  });

  it("returns the last fraction above the last breakpoint", () => {
    expect(tokenToFraction(999, breakpoints)).toBe(1);
  });

  it("returns 0 for no breakpoints", () => {
    expect(tokenToFraction(50, [])).toBe(0);
  });

  it("stays finite when two breakpoints share a token", () => {
    const flat = [
      { token: 0, fraction: 0 },
      { token: 100, fraction: 0.2 },
      { token: 100, fraction: 0.6 },
    ];
    expect(tokenToFraction(100, flat)).toBe(0.2);
    expect(tokenToFraction(150, flat)).toBe(0.6);
  });
});
