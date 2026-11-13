import { polygonContains } from "d3-polygon";
import type { Hull, LaidOutNode } from "./graphLayout";

/**
 * Geometry for graph labels: the label box, where it sits around a dot, how wide a text is, and
 * whether a box touches a line, an outline or a dot.
 */

type Point = [number, number];

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LabelBox extends Rect {
  id: number;
  text: string;
  /** The untruncated source text, when `text` is ellipsized; for a full-text `<title>`. */
  fullText?: string;
  /** Set when the label sits away from its dot: the line that joins them, in the graph's px coordinates. */
  leader?: { x1: number; y1: number; x2: number; y2: number };
  /**
   * Where the text is drawn and which of its ends sits there. A label beside its dot is anchored
   * on the end nearest the dot, so the gap holds whatever the real glyph width turns out to be.
   * Omitted when the text starts `GLYPH_LEFT_PX` in from the box's left edge.
   */
  textX?: number;
  textAnchor?: "start" | "middle" | "end";
  /** Set when no clean spot was left and a rule was relaxed; 1 is the first relaxation. */
  relaxed?: number;
  /**
   * Only in the related graph: the whole name broken at a space into two lines, both on `textX`
   * and `textAnchor`. `text` is then the whole name and the box is one line taller.
   */
  lines?: [string, string];
}

export const LABEL_LINE_HEIGHT = 14;
/** The font size, in px, that labels are drawn at unless a caller says otherwise. */
export const LABEL_FONT_PX = 12;

/**
 * Padding on every side of a label box for its halo, the outline drawn around the text, which
 * paints wider than the glyphs. It also absorbs the small error in the canvas-based width estimate.
 */
export const LABEL_HALO_PAD = 3;

/** A label box is this much wider than its text, on top of the halo padding on each side. */
const LABEL_EXTRA_WIDTH_PX = 4;

/**
 * The page narrows its sans text with `font-stretch`, which a canvas measurement does not apply.
 * This ratio scales the measurement toward the drawn width.
 */
const PAGE_STRETCH_RATIO = 0.93;

/** Returns the width of the box of a label whose text is `textWidth` px wide. */
export function boxWidthFor(textWidth: number): number {
  return textWidth + LABEL_EXTRA_WIDTH_PX + LABEL_HALO_PAD * 2;
}

/**
 * Returns the rendered width of `text` in px at `fontPx`, measured on a canvas where one exists.
 * Under jsdom, which has no canvas, it falls back to a fixed per-character estimate that stays the
 * same between runs.
 */
export function measureTextWidth(text: string, fontPx: number): number {
  if (typeof document !== "undefined") {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.font = `${fontPx}px "Archivo Variable", "Helvetica Neue", Arial, sans-serif`;
      return ctx.measureText(text).width * PAGE_STRETCH_RATIO;
    }
  }
  return text.length * fontPx * 0.56;
}

/**
 * Shortens a title to at most `max` characters, ending in `...`.
 * It cuts at the last space unless that would drop more than half of the kept text.
 */
export function ellipsize(text: string, max: number): string {
  if (text.length <= max) {
    return text;
  }
  const hardCut = Math.max(0, max - 3);
  const slice = text.slice(0, hardCut);
  // Cut at the last space instead of mid-word, unless that space is in the first half of the slice.
  // A title with one long word then keeps the hard cut instead of collapsing to almost nothing.
  const lastSpace = slice.lastIndexOf(" ");
  const cut = lastSpace >= hardCut / 2 ? slice.slice(0, lastSpace) : slice;
  return `${cut}...`;
}

export function boxesOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

/** Counts the pairs of label boxes that overlap. */
export function countLabelCollisions(boxes: LabelBox[]): number {
  let collisions = 0;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      if (a && b && boxesOverlap(a, b)) {
        collisions += 1;
      }
    }
  }
  return collisions;
}

function turn(p: Point, q: Point, r: Point): number {
  return Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
}

export function segmentsCross(a: Point, b: Point, c: Point, d: Point): boolean {
  return turn(a, b, c) !== turn(a, b, d) && turn(c, d, a) !== turn(c, d, b);
}

function pointInRect(p: Point, box: Rect): boolean {
  return p[0] >= box.x && p[0] <= box.x + box.width && p[1] >= box.y && p[1] <= box.y + box.height;
}

/** The four sides of a rect, in the order top, right, bottom, left. */
function rectSides(box: Rect): Array<[Point, Point]> {
  const topLeft: Point = [box.x, box.y];
  const topRight: Point = [box.x + box.width, box.y];
  const bottomLeft: Point = [box.x, box.y + box.height];
  const bottomRight: Point = [box.x + box.width, box.y + box.height];
  return [
    [topLeft, topRight],
    [topRight, bottomRight],
    [bottomRight, bottomLeft],
    [bottomLeft, topLeft],
  ];
}

/** True when a hull's outline runs through the box. A box wholly inside or outside the hull does not count. */
export function boxCrossesOutline(box: Rect, hull: Hull): boolean {
  if (hull.points.some((point) => pointInRect(point, box))) {
    return true;
  }
  const sides = rectSides(box);
  return hull.points.some((point, index) => {
    const next = hull.points[(index + 1) % hull.points.length]!;
    return sides.some(([from, to]) => segmentsCross(point, next, from, to));
  });
}

/** True when any part of a hull's outline or fill lies under the box. */
export function boxTouchesHull(box: Rect, hull: Hull): boolean {
  const corners: Point[] = [
    [box.x, box.y],
    [box.x + box.width, box.y],
    [box.x, box.y + box.height],
    [box.x + box.width, box.y + box.height],
    [box.x + box.width / 2, box.y + box.height / 2],
  ];
  return (
    corners.some((point) => polygonContains(hull.points, point)) || boxCrossesOutline(box, hull)
  );
}

export type Anchor =
  | "right"
  | "left"
  | "above"
  | "below"
  | "above-right"
  | "above-left"
  | "below-right"
  | "below-left";

export const ALL_DIAGONALS: Anchor[] = ["above-right", "above-left", "below-right", "below-left"];

/**
 * A label must clear every other dot by this much more than its own dot, so its nearest dot is its
 * own.
 */
export const OWN_DOT_MARGIN_PX = 3;

/** How far in from the box's left edge the text starts. */
export const GLYPH_LEFT_PX = 2;
/** How far in from the box's right edge the text ends, for a box built by `boxWidthFor`. */
const GLYPH_RIGHT_PX = boxWidthFor(0) - GLYPH_LEFT_PX;
/** The bottom of the glyphs, measured down from the top of a one-line box. */
export const GLYPH_BOTTOM_PX = LABEL_LINE_HEIGHT + LABEL_HALO_PAD * 2 - 1;
/**
 * The height of a line of text at the default font size: the font's ascent plus its descent, which
 * is a little over one em.
 */
const GLYPH_HEIGHT_PX = 13;
/** The top of the glyphs, measured down from the top of a one-line box. */
export const GLYPH_TOP_PX = GLYPH_BOTTOM_PX - GLYPH_HEIGHT_PX;

interface Placement {
  bx: number;
  by: number;
  textX: number;
  textAnchor: "start" | "middle" | "end";
}

/**
 * Returns a label box's top-left corner and text origin for one of 8 anchors around a node: 4
 * sides and 4 diagonals.
 *
 * Anchors are laid out on the glyphs, so the text ends up `gapPx` from the dot's edge.
 * `extraHeightPx` is how much taller than one line the box is, such as for a two-line name, and
 * the text keeps the same clearance.
 */
export function anchorPosition(
  anchor: Anchor,
  nodeX: number,
  nodeY: number,
  radius: number,
  gapPx: number,
  boxW: number,
  extraHeightPx = 0,
): Placement {
  const reach = radius + gapPx;
  const diag = reach * Math.SQRT1_2;
  const midY = nodeY - (GLYPH_TOP_PX + GLYPH_BOTTOM_PX + extraHeightPx) / 2;
  const rightOf = (dx: number, by: number) => ({
    bx: nodeX + dx - GLYPH_LEFT_PX,
    by,
    textX: nodeX + dx,
    textAnchor: "start" as const,
  });
  const leftOf = (dx: number, by: number) => ({
    bx: nodeX - dx - boxW + GLYPH_RIGHT_PX,
    by,
    textX: nodeX - dx,
    textAnchor: "end" as const,
  });
  const centred = (by: number) => ({
    bx: nodeX - boxW / 2,
    by,
    textX: nodeX,
    textAnchor: "middle" as const,
  });
  const aboveY = nodeY - diag - GLYPH_BOTTOM_PX - extraHeightPx;
  const belowY = nodeY + diag - GLYPH_TOP_PX;
  const places: Record<Anchor, () => Placement> = {
    right: () => rightOf(reach, midY),
    left: () => leftOf(reach, midY),
    above: () => centred(nodeY - reach - GLYPH_BOTTOM_PX - extraHeightPx),
    below: () => centred(nodeY + reach - GLYPH_TOP_PX),
    "above-right": () => rightOf(diag, aboveY),
    "above-left": () => leftOf(diag, aboveY),
    "below-right": () => rightOf(diag, belowY),
    "below-left": () => leftOf(diag, belowY),
  };
  return places[anchor]();
}

/** Distance from a box to a circle's edge; 0 when they overlap. */
export function boxCircleDistance(box: Rect, n: LaidOutNode): number {
  const nearX = Math.min(Math.max(n.x, box.x), box.x + box.width);
  const nearY = Math.min(Math.max(n.y, box.y), box.y + box.height);
  return Math.max(0, Math.hypot(n.x - nearX, n.y - nearY) - n.radius);
}

/** The leader line from a dot's edge to the nearest point of its label's text box. */
export function leaderFor(box: LabelBox, node: LaidOutNode): LabelBox["leader"] {
  const inner = {
    left: box.x + LABEL_HALO_PAD,
    right: box.x + box.width - LABEL_HALO_PAD,
    top: box.y + LABEL_HALO_PAD,
    bottom: box.y + box.height - LABEL_HALO_PAD,
  };
  const x2 = Math.min(Math.max(node.x, inner.left), inner.right);
  const y2 = Math.min(Math.max(node.y, inner.top), inner.bottom);
  const length = Math.hypot(x2 - node.x, y2 - node.y) || 1;
  return {
    x1: node.x + ((x2 - node.x) / length) * node.radius,
    y1: node.y + ((y2 - node.y) / length) * node.radius,
    x2,
    y2,
  };
}

/**
 * Places the name of one dot that carries no permanent label, such as the hovered, focused or
 * selected dot, in the same label style.
 *
 * It takes the first of 8 positions that is inside the frame and clear of every box in `placed` and
 * every other dot, else the first clear of the boxes, else the first inside, else the first
 * position. It never moves another label.
 */
export function placeDotName(
  node: LaidOutNode,
  placed: LabelBox[],
  others: LaidOutNode[],
  options: {
    width: number;
    height: number;
    fontPx?: number;
    gapPx?: number;
    ellipsisChars?: number;
  },
): LabelBox {
  const { width, height, fontPx = LABEL_FONT_PX, gapPx = 4, ellipsisChars = 26 } = options;
  const text = ellipsize(node.title, ellipsisChars);
  const boxW = boxWidthFor(measureTextWidth(text, fontPx));
  const boxH = LABEL_LINE_HEIGHT + LABEL_HALO_PAD * 2;
  const awayX: "right" | "left" = node.x >= width / 2 ? "right" : "left";
  const awayY: "above" | "below" = node.y >= height / 2 ? "below" : "above";
  const diagPrimary: Anchor = `${awayY}-${awayX}`;
  const order: Anchor[] = [
    awayX,
    awayY,
    awayX === "right" ? "left" : "right",
    awayY === "below" ? "above" : "below",
    diagPrimary,
    ...ALL_DIAGONALS.filter((d) => d !== diagPrimary),
  ];
  const boxes = order.map((anchor): LabelBox => {
    const { bx, by, textX, textAnchor } = anchorPosition(
      anchor,
      node.x,
      node.y,
      node.radius,
      gapPx,
      boxW,
    );
    return {
      id: node.id,
      x: bx,
      y: by,
      width: boxW,
      height: boxH,
      text,
      fullText: text === node.title ? undefined : node.title,
      textX,
      textAnchor,
    };
  });
  const inside = (box: LabelBox) =>
    box.x >= 0 && box.y >= 0 && box.x + box.width <= width && box.y + box.height <= height;
  const clearOfLabels = (box: LabelBox) =>
    inside(box) && !placed.some((other) => boxesOverlap(box, other));
  const clearOfDots = (box: LabelBox) =>
    others.every((other) => other.id === node.id || boxCircleDistance(box, other) >= 1);
  return (
    boxes.find((box) => clearOfLabels(box) && clearOfDots(box)) ??
    boxes.find(clearOfLabels) ??
    boxes.find(inside) ??
    boxes[0]!
  );
}
