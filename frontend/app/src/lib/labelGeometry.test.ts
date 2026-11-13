import { describe, expect, it } from "vitest";
import type { Hull, LaidOutNode } from "./graphLayout";
import {
  anchorPosition,
  boxCircleDistance,
  boxCrossesOutline,
  boxTouchesHull,
  boxWidthFor,
  boxesOverlap,
  countLabelCollisions,
  ellipsize,
  leaderFor,
  measureTextWidth,
  placeDotName,
  segmentsCross,
  type Anchor,
  type LabelBox,
} from "./labelGeometry";

const dot = (id: number, x: number, y: number, radius = 6, title = `Dot ${id}`): LaidOutNode => ({
  id,
  title,
  views: 1,
  x,
  y,
  radius,
  cluster: 0,
});
const others = (node: LaidOutNode) => [node];
const labelBox = (x: number, y: number, width: number, height: number): LabelBox => ({
  id: -1,
  x,
  y,
  width,
  height,
  text: "",
});

describe("ellipsize", () => {
  it.each([
    ["leaves a title that fits untouched", "Alan Turing", 26, "Alan Turing"],
    [
      "cuts a long title at a word boundary",
      "Monster: The Lizzie Borden Story (2026 miniseries)",
      26,
      "Monster: The Lizzie...",
    ],
    [
      "cuts one long word hard, since a cut at the first space would keep too little",
      "Supercalifragilisticexpialidocious-the-full-article-title",
      12,
      "Supercali...",
    ],
    ["cuts a title with no space hard", "Wolfeschlegelsteinhausen", 10, "Wolfesc..."],
  ])("%s", (_name, text, max, expected) => {
    expect(ellipsize(text, max)).toBe(expected);
  });
});

describe("boxWidthFor", () => {
  it("adds the halo padding on both sides and the extra room to the text width", () => {
    // 3px halo on each side plus 4px of extra room.
    expect(boxWidthFor(50)).toBe(60);
  });
});

describe("measureTextWidth", () => {
  it("falls back to a per-character estimate where there is no canvas", () => {
    expect(measureTextWidth("abcd", 10)).toBeCloseTo(22.4, 5);
    expect(measureTextWidth("abcd", 20)).toBeCloseTo(44.8, 5);
  });
});

describe("boxesOverlap and countLabelCollisions", () => {
  it.each([
    ["boxes that share area", labelBox(0, 0, 10, 10), labelBox(5, 5, 10, 10), true],
    ["boxes that only touch along an edge", labelBox(0, 0, 10, 10), labelBox(10, 0, 10, 10), false],
    ["boxes far apart", labelBox(0, 0, 10, 10), labelBox(50, 50, 10, 10), false],
  ])("treats %s", (_name, a, b, overlaps) => {
    expect(boxesOverlap(a, b)).toBe(overlaps);
  });

  it("counts every overlapping pair once", () => {
    const boxes = [labelBox(0, 0, 10, 10), labelBox(5, 5, 10, 10), labelBox(8, 8, 10, 10)];
    expect(countLabelCollisions(boxes)).toBe(3);
    expect(countLabelCollisions([boxes[0]!, labelBox(50, 50, 5, 5)])).toBe(0);
  });
});

describe("segmentsCross", () => {
  it.each<
    [string, [number, number], [number, number], [number, number], [number, number], boolean]
  >([
    ["segments that form an X", [0, 0], [10, 10], [0, 10], [10, 0], true],
    ["parallel segments", [0, 0], [10, 0], [0, 5], [10, 5], false],
    ["collinear segments that do not meet", [0, 0], [4, 0], [6, 0], [10, 0], false],
    ["a segment that stops short of the other", [0, 0], [4, 4], [0, 10], [10, 0], false],
  ])("is right for %s", (_name, a, b, c, d, crosses) => {
    expect(segmentsCross(a, b, c, d)).toBe(crosses);
  });
});

describe("boxTouchesHull and boxCrossesOutline", () => {
  const hull: Hull = {
    cluster: 0,
    points: [
      [0, 0],
      [100, 0],
      [100, 100],
      [0, 100],
    ],
  };
  it.each([
    ["inside the hull", labelBox(40, 40, 20, 20), true, false],
    ["across one of its sides", labelBox(90, 40, 40, 20), true, true],
    ["across a corner", labelBox(90, 90, 30, 30), true, true],
    ["around the whole hull", labelBox(-10, -10, 120, 120), true, true],
    ["outside the hull", labelBox(150, 40, 20, 20), false, false],
  ])("a box %s", (_name, box, touches, crosses) => {
    expect(boxTouchesHull(box, hull)).toBe(touches);
    expect(boxCrossesOutline(box, hull)).toBe(crosses);
  });

  it("sees a hull that crosses a box without any corner or vertex inside the other", () => {
    // A thin box laid across the hull: its corners are outside the hull and no hull vertex is inside it.
    const thin = labelBox(-20, 45, 140, 10);
    expect(boxCrossesOutline(thin, hull)).toBe(true);
    expect(boxTouchesHull(thin, hull)).toBe(true);
  });
});

describe("anchorPosition", () => {
  // A dot at (100, 200) of radius 6 with a 4px gap reaches 10px; the box is 60px wide.
  const reach = 10;
  const diag = reach * Math.SQRT1_2;
  const cases: Array<[Anchor, number, number, number, "start" | "middle" | "end"]> = [
    // [anchor, bx, by, textX, textAnchor]; the glyphs span 6px to 19px down a one-line box.
    ["right", 100 + reach - 2, 200 - 12.5, 100 + reach, "start"],
    ["left", 100 - reach - 60 + 8, 200 - 12.5, 100 - reach, "end"],
    ["above", 100 - 30, 200 - reach - 19, 100, "middle"],
    ["below", 100 - 30, 200 + reach - 6, 100, "middle"],
    ["above-right", 100 + diag - 2, 200 - diag - 19, 100 + diag, "start"],
    ["above-left", 100 - diag - 60 + 8, 200 - diag - 19, 100 - diag, "end"],
    ["below-right", 100 + diag - 2, 200 + diag - 6, 100 + diag, "start"],
    ["below-left", 100 - diag - 60 + 8, 200 + diag - 6, 100 - diag, "end"],
  ];
  it.each(cases)(
    "puts the text of a %s label gapPx from the dot's edge",
    (anchor, bx, by, textX, textAnchor) => {
      const place = anchorPosition(anchor, 100, 200, 6, 4, 60);
      expect(place.bx).toBeCloseTo(bx, 5);
      expect(place.by).toBeCloseTo(by, 5);
      expect(place.textX).toBeCloseTo(textX, 5);
      expect(place.textAnchor).toBe(textAnchor);
    },
  );

  it("keeps the clearance of a taller box by growing it upward on the above anchors and centring it on the sides", () => {
    expect(anchorPosition("above", 100, 200, 6, 4, 60, 14).by).toBeCloseTo(
      200 - reach - 19 - 14,
      5,
    );
    expect(anchorPosition("right", 100, 200, 6, 4, 60, 14).by).toBeCloseTo(
      200 - (6 + 19 + 14) / 2,
      5,
    );
    expect(anchorPosition("below", 100, 200, 6, 4, 60, 14).by).toBeCloseTo(200 + reach - 6, 5);
  });
});

describe("boxCircleDistance", () => {
  it.each([
    ["a box to the side of the dot", labelBox(20, -5, 10, 10), 15],
    ["a box diagonal to the dot", labelBox(8, 8, 10, 10), Math.hypot(8, 8) - 5],
    ["a box the dot overlaps", labelBox(2, -5, 10, 10), 0],
  ])("measures %s from the dot's edge", (_name, box, expected) => {
    expect(boxCircleDistance(box, dot(1, 0, 0, 5))).toBeCloseTo(expected, 5);
  });
});

describe("leaderFor", () => {
  it("runs from the dot's edge to the nearest point of the text box inside its halo padding", () => {
    // The text box starts 3px in from the label box's left edge and spans the dot's row.
    const leader = leaderFor(labelBox(20, 40, 60, 20), dot(1, 0, 50, 4));
    expect(leader).toEqual({ x1: 4, y1: 50, x2: 23, y2: 50 });
  });

  it("is a point on the dot's centre when the dot sits inside its own text box", () => {
    const leader = leaderFor(labelBox(0, 0, 60, 20), dot(1, 30, 10, 4));
    expect(leader).toEqual({ x1: 30, y1: 10, x2: 30, y2: 10 });
  });
});

describe("placeDotName", () => {
  const frame = { width: 400, height: 400 };

  it("takes the position on the side facing away from the middle of the frame first", () => {
    const node = dot(1, 300, 100);
    const box = placeDotName(node, [], others(node), frame);
    expect(box.textAnchor).toBe("start");
    expect(box.textX).toBe(300 + 6 + 4);
    expect(box.id).toBe(1);
  });

  it("moves to the next position when a placed label is in the way", () => {
    const node = dot(1, 300, 100);
    const free = placeDotName(node, [], others(node), frame);
    const blocked = placeDotName(node, [{ ...free }], others(node), frame);
    expect(blocked.textAnchor).not.toBe(free.textAnchor);
    expect(boxesOverlap(blocked, free)).toBe(false);
  });

  it.each([
    [
      "below a dot in the lower half",
      300,
      300,
      (box: LabelBox) => expect(box.y).toBeGreaterThan(300),
    ],
    [
      "above a dot in the upper half",
      300,
      100,
      (box: LabelBox) => expect(box.y + box.height).toBeLessThan(100),
    ],
  ])("tries the vertical position next, %s", (_name, x, y, check) => {
    const node = dot(1, x, y);
    // A thin label across the side position, clear of the position above or below.
    const thin = labelBox(x + 10, y - 3, 60, 6);
    const box = placeDotName(node, [thin], others(node), frame);
    expect(box.textAnchor).toBe("middle");
    check(box);
  });

  it("takes the first position clear of the other labels when every position meets another dot", () => {
    const node = dot(1, 300, 200);
    const side = placeDotName(node, [], others(node), frame);
    // A ring of dots close enough to touch every position, and a label on the first one.
    const ring = Array.from({ length: 16 }, (_, i) =>
      dot(
        10 + i,
        300 + 40 * Math.cos((i * Math.PI) / 8),
        200 + 40 * Math.sin((i * Math.PI) / 8),
        12,
      ),
    );
    const box = placeDotName(node, [{ ...side }], [node, ...ring], frame);
    expect(boxesOverlap(box, side)).toBe(false);
  });

  it("takes the first position inside the frame when every position meets another label", () => {
    const node = dot(1, 396, 200);
    const everywhere = labelBox(0, 0, frame.width, frame.height);
    const box = placeDotName(node, [everywhere], others(node), frame);
    expect(box.x + box.width).toBeLessThanOrEqual(frame.width);
  });

  it("moves to another dot-free position when another dot is in the way", () => {
    const node = dot(1, 300, 100);
    const free = placeDotName(node, [], others(node), frame);
    const neighbour = dot(2, free.x + free.width / 2, free.y + free.height / 2, 3);
    const moved = placeDotName(node, [], [node, neighbour], frame);
    expect(boxCircleDistance(moved, neighbour)).toBeGreaterThanOrEqual(1);
  });

  it("keeps the label inside the frame where a free position inside exists", () => {
    const node = dot(1, 396, 100);
    const box = placeDotName(node, [], others(node), frame);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(frame.width);
  });

  it.each([
    [
      "cuts a long title and keeps the whole one for the tooltip",
      "A title that is far too long to fit",
      10,
      "A title...",
      "A title that is far too long to fit",
    ],
    ["leaves a short title whole", "Short", 26, "Short", undefined],
  ])("%s", (_name, title, ellipsisChars, text, fullText) => {
    const node = dot(1, 300, 100, 6, title);
    const box = placeDotName(node, [], others(node), { ...frame, ellipsisChars });
    expect(box.text).toBe(text);
    expect(box.fullText).toBe(fullText);
  });
});
