import type { GraphEdge, Hull, LaidOutNode } from "./graphLayout";
import {
  ALL_DIAGONALS,
  GLYPH_BOTTOM_PX,
  GLYPH_LEFT_PX,
  GLYPH_TOP_PX,
  LABEL_FONT_PX,
  LABEL_HALO_PAD,
  LABEL_LINE_HEIGHT,
  OWN_DOT_MARGIN_PX,
  anchorPosition,
  boxCircleDistance,
  boxCrossesOutline,
  boxTouchesHull,
  boxWidthFor,
  boxesOverlap,
  ellipsize,
  leaderFor,
  measureTextWidth,
  segmentsCross,
  type Anchor,
  type LabelBox,
  type Rect,
} from "./labelGeometry";

/**
 * Chooses which dots of the concept graph get a name and where each name stands, without regard to hover, focus or selection.
 * The index variant names dots in tiers, groups of dots placed in turn, by views and leaves the rest unnamed.
 * The related variant tries to name every dot and prices each spot by the lines and outlines under it.
 */

/** Number of most-viewed dots that the index variant places before any other dot. */
export const ALWAYS_NAMED = 10;
/** A dot with no other dot within this many px, centre to centre, is isolated. This is the radius unless `phone` is set. */
const ISOLATED_RADIUS_DEFAULT_PX = 90;
const ISOLATED_RADIUS_PHONE_PX = 56;
/** The last index tier skips a dot whose grid cell already holds a name. This is the cell size when neither `phone` nor `desktop` is set. */
const CELL_DEFAULT_PX = 120;
const CELL_PHONE_PX = 72;
/** Grid cell used when the `desktop` option is set and `phone` is not. A wide graph has room for names closer together. */
const CELL_WIDE_PX = 108;
/** Gaps between a dot's edge and its name: beside it, on the near ring or on the far ring. A name on the near or far ring always has a leader. */
const RING_BESIDE_PX = 4;
const RING_NEAR_PX = 14;
const RING_FAR_PX = 28;
/** Fourth ring, added only when the `desktop` option is set so that a name has more spots to choose from. */
const RING_OUTER_PX = 34;
/** Without the `desktop` option, no name stands farther than this from its dot's edge. */
const MAX_GAP_PX = 29.5;
/** Replaces MAX_GAP_PX when the `desktop` option is set. */
const MAX_GAP_DESKTOP_PX = 36;
/** Shortest length, ellipsis included, that a cut name is tried at. The last-resort search uses MIN_CUT_CHARS_LAST_RESORT instead. */
const MIN_CUT_CHARS = 9;
/** Default for the fewest characters a cut name shows ahead of its ellipsis. A shorter cut is not tried, except by bestEffort. */
const MIN_VISIBLE_CHARS = 8;
/** Fewest characters a cut name shows ahead of its ellipsis in bestEffort, the related variant's last resort. */
const MIN_VISIBLE_CHARS_LAST_RESORT = 5;
/** Shortest length, ellipsis included, that bestEffort cuts a name to. */
const MIN_CUT_CHARS_LAST_RESORT = 5;
/** A wording wider than this share of the frame width is dropped, so a name does not run edge to edge. When every wording is wider, only the last one is kept. */
const WIDEST_NAME_SHARE = 0.9;
/**
 * The related variant prices each spot instead of forbidding lines under a name.
 * NEAR_RING_COST is just above LINE_COST, so a name accepts one line under it before it takes a leader.
 * CUT_COST is above two lines plus FAR_RING_COST, so a name stays whole wherever a leader and two lines can reach it.
 */
const LINE_COST = 10;
const OUTLINE_COST = 5;
const NEAR_RING_COST = 11;
const FAR_RING_COST = 14;
const CUT_COST = 36;
/** A cut also costs this much for each character it drops. */
const CUT_COST_PER_CHAR = 0.4;
/** A dot under a name costs this much in bestEffort, far more than a line or an outline. */
const DOT_UNDER_COST = 100;
/** In bestEffort, each step down the list of wordings, from the whole name to a shorter cut, costs this much. */
const WORDING_STEP_COST = 3;
/**
 * A two-line name costs more than FAR_RING_COST, so a clear one-line spot wins.
 * It costs less than CUT_COST, so two lines are preferred to a cut.
 */
const TWO_LINE_COST = 16;
/** Each line of a two-line name holds at most this many characters. */
const LINE_MAX_CHARS = 26;
/** A cut name is swapped for a longer cut only when the longer one shows at most this many characters ahead of its ellipsis. */
const STUB_MAX_CHARS = 26;
/** A longer cut may stand on a spot that costs up to this many lines' worth more than the chosen cut's spot. */
const STUB_EXTRA_LINES = 2;
/** Breathing room kept between a name's glyphs and a line or outline. */
const LINE_CLEARANCE_PX = 2;
/** Space kept between a name's glyphs and every edge of the frame. */
const FRAME_MARGIN_PX = 7;
/** Breathing room kept between a leader and another name or dot. */
const LEADER_CLEARANCE_PX = 1;
/** On the related variant, a name beside its dot gets a leader, where one fits, when another dot is less than this much farther from it than its own. */
const NEIGHBOUR_DOT_MARGIN_PX = 12;
/**
 * Number of evenly spaced directions tried around a dot, in addition to the eight anchors, on every ring but the beside ring.
 * It applies when a search is allowed the finer directions, and cleanSpots counts them on every ring.
 */
const FINE_DIRECTIONS = 16;
/** The height of a one-line label box. */
const LINE_BOX_HEIGHT = LABEL_LINE_HEIGHT + LABEL_HALO_PAD * 2;
/** The height of a two-line label box. */
const TWO_LINE_BOX_HEIGHT = LABEL_LINE_HEIGHT * 2 + LABEL_HALO_PAD * 2;
/** How far in from a label box's edge centred text starts; start and end text start GLYPH_LEFT_PX in. */
const CENTRED_INSET_PX = boxWidthFor(0) / 2;
/** How far above a box's bottom edge its glyphs end. */
const GLYPH_BOTTOM_INSET_PX = LINE_BOX_HEIGHT - GLYPH_BOTTOM_PX;

export interface LabelPlacementOptions {
  /** The index graph or the related graph. */
  variant: "index" | "related";
  /** Uses the smaller isolation radius and grid cell, for a narrow screen. */
  phone?: boolean;
  /** Dots placed before the others, such as the seed of the related graph. A dot is still left unnamed when no spot is free. */
  alwaysShowIds?: Set<number>;
  /** The edges drawn between the dots, so a name can keep off them. */
  edges?: GraphEdge[];
  /** Font size in px that the names are drawn at; defaults to LABEL_FONT_PX. */
  fontPx?: number;
  /** Fewest characters a cut name shows ahead of its ellipsis; a shorter cut is not tried. Defaults to MIN_VISIBLE_CHARS. */
  minVisibleChars?: number;
  /** Longest a name may be in characters, ellipsis included. Left out, a name is cut only when a cut fits better than its whole text. */
  ellipsisChars?: number;
  width: number;
  height: number;
  /** Boxes of other elements drawn over the graph, such as the stats chip or the legend chip. No name may overlap them. */
  reservedBoxes?: LabelBox[];
  /**
   * Flips once the label font has loaded, so a caller that memoises on these options re-measures
   * the names.
   */
  fontsReady?: boolean;
  /**
   * Gives names more room on a wide graph: a smaller grid cell, leaders up to MAX_GAP_DESKTOP_PX, and a fourth ring of spots.
   * The index variant also tries the finer directions on every tier below the first.
   * The collision rules stay: a leader may cross a line but never a name, a dot or another leader.
   */
  desktop?: boolean;
}

interface Rules {
  /** Keep off the lines between dots. */
  edges: boolean;
  /** Keep off the dot's own group outline. */
  ownOutline: boolean;
  /** Keep off the outlines of the other groups. */
  foreignOutlines: boolean;
}

const STRICT: Rules = {
  edges: true,
  ownOutline: true,
  foreignOutlines: true,
};
const RELAX_OUTLINE: Rules = { ...STRICT, ownOutline: false };
const RELAX_EDGES: Rules = { ...RELAX_OUTLINE, edges: false };
/** Rules of the related variant: a line or outline under a name is priced instead of forbidden. Dots and other names stay forbidden in every rule set. */
const PRICED: Rules = { ...RELAX_EDGES, foreignOutlines: false };
/** The rules tried in turn for a name that must be placed. The related variant then falls back to bestEffort when a cut is allowed. */
const MUST_RULES: Rules[] = [STRICT, RELAX_OUTLINE, RELAX_EDGES];

type Point = [number, number];
type Segment = [Point, Point];

/**
 * One way to write a name: its text, the width of its box and, on two lines, the lines and the
 * box's height.
 */
interface Wording {
  text: string;
  fullText?: string;
  boxW: number;
  lines?: [string, string];
  boxH?: number;
}

/** A spot that passed the rules, with its price and whether a group outline runs under it. */
interface Scored {
  box: LabelBox;
  cost: number;
  outline: boolean;
}

/**
 * How to place a name whole later: the rings and directions of the search that first placed it,
 * or "must" for a name placed by `placeMust`.
 */
type WholeRecipe = { rings: number[]; fine: boolean } | "must";

/** One group of dots that the index variant places in turn. */
interface Tier {
  ids: LaidOutNode[];
  rules: Rules[];
  rings: number[];
  /** A dot whose grid cell already holds a name is skipped. */
  oneInCell: boolean;
  /** The finer directions are tried as well as the eight anchors. */
  fine: boolean;
  /** Every dot is placed by `placeMust`, the one with the fewest free spots first. */
  must: boolean;
}

/** The inputs of one `computeLabelPlacements` call, the lookups derived from them and the names placed so far. */
interface Run {
  nodes: LaidOutNode[];
  hulls: Hull[];
  variant: "index" | "related";
  phone: boolean;
  desktop: boolean;
  alwaysShowIds: Set<number>;
  fontPx: number;
  minVisibleChars: number;
  ellipsisChars: number;
  width: number;
  height: number;
  reservedBoxes: LabelBox[];
  /** The farthest a name may stand from its dot's edge. */
  maxGap: number;
  /** The grid cell size of the last index tier. */
  cell: number;
  /** The drawn edges, as segments between the dots' centres. */
  segments: Segment[];
  /** The dots by views, highest first. */
  ranked: LaidOutNode[];
  /** The label box of every dot, or null while it has none. */
  placements: Map<number, LabelBox | null>;
  /** The reserved boxes and every name placed so far. */
  placedBoxes: LabelBox[];
  /** The leader of every name placed so far, as a segment. */
  placedLeaders: Segment[];
  /** The grid cells that hold a name. */
  usedCells: Set<string>;
  /** How to place each name whole, by node id. */
  wholeRecipes: Map<number, WholeRecipe>;
}

/**
 * Breaks a name at a space into two lines of at most LINE_MAX_CHARS each, preferring the break whose longer line is shortest, which is also the most even pair.
 * The earlier break wins a tie, and the result is null when no break fits.
 */
export function breakIntoTwoLines(title: string): [string, string] | null {
  let best: [string, string] | null = null;
  let bestLongest = Number.POSITIVE_INFINITY;
  for (let i = title.indexOf(" "); i !== -1; i = title.indexOf(" ", i + 1)) {
    const first = title.slice(0, i);
    const second = title.slice(i + 1);
    const longest = Math.max(first.length, second.length);
    if (
      first.length > 0 &&
      second.length > 0 &&
      longest <= LINE_MAX_CHARS &&
      longest < bestLongest
    ) {
      best = [first, second];
      bestLongest = longest;
    }
  }
  return best;
}

/** Returns the ids of dots that have no other dot within `radius` px, centre to centre. */
export function isolatedIds(nodes: LaidOutNode[], radius: number): Set<number> {
  const ids = new Set<number>();
  for (const n of nodes) {
    if (nodes.every((o) => o.id === n.id || Math.hypot(o.x - n.x, o.y - n.y) >= radius)) {
      ids.add(n.id);
    }
  }
  return ids;
}

function inflate(r: Rect, by: number): Rect {
  return { x: r.x - by, y: r.y - by, width: r.width + 2 * by, height: r.height + 2 * by };
}

/** Returns the area the text of a label box covers; the box adds padding for the outline drawn around the text. */
export function glyphsOf(box: Rect & { textAnchor?: "start" | "middle" | "end" }): Rect {
  const left = box.textAnchor === "middle" ? CENTRED_INSET_PX : GLYPH_LEFT_PX;
  return {
    x: box.x + left,
    y: box.y + GLYPH_TOP_PX,
    width: box.width - boxWidthFor(0),
    height: box.height - GLYPH_TOP_PX - GLYPH_BOTTOM_INSET_PX,
  };
}

function segmentHitsRect(a: Point, b: Point, r: Rect): boolean {
  const inside = (p: Point) =>
    p[0] >= r.x && p[0] <= r.x + r.width && p[1] >= r.y && p[1] <= r.y + r.height;
  if (inside(a) || inside(b)) {
    return true;
  }
  const tl: Point = [r.x, r.y];
  const tr: Point = [r.x + r.width, r.y];
  const bl: Point = [r.x, r.y + r.height];
  const br: Point = [r.x + r.width, r.y + r.height];
  return (
    segmentsCross(a, b, tl, tr) ||
    segmentsCross(a, b, tr, br) ||
    segmentsCross(a, b, br, bl) ||
    segmentsCross(a, b, bl, tl)
  );
}

function pointSegmentDistance(px: number, py: number, a: Point, b: Point): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / len2));
  return Math.hypot(a[0] + t * dx - px, a[1] + t * dy - py);
}

/** Returns the text of a cut name ahead of its ellipsis. */
function visibleStart(text: string): string {
  return text.replace(/\.{3}$/, "").trimEnd();
}

/** The whole title a label stands for. */
function fullOf(box: LabelBox): string {
  return box.fullText ?? box.text;
}

/** How much of a name is shown, -1 when it is not. */
function keptLength(box: LabelBox | null | undefined): number {
  return box ? box.text.length : -1;
}

function byViews(a: LaidOutNode, b: LaidOutNode): number {
  return (b.views ?? -1) - (a.views ?? -1) || a.id - b.id;
}

/** Returns true when a cut of `title` ends inside a word, not at a space. */
function endsInsideWord(title: string, cut: string): boolean {
  return title.charAt(visibleStart(cut).length) !== " ";
}

/** Returns the price of a ring: how much more a name standing on it costs than one beside its dot. */
function ringCost(gap: number): number {
  if (gap === RING_BESIDE_PX) {
    return 0;
  }
  return gap === RING_NEAR_PX ? NEAR_RING_COST : FAR_RING_COST;
}

function createRun(nodes: LaidOutNode[], hulls: Hull[], options: LabelPlacementOptions): Run {
  const {
    variant,
    phone = false,
    alwaysShowIds = new Set<number>(),
    edges = [],
    fontPx = LABEL_FONT_PX,
    minVisibleChars = MIN_VISIBLE_CHARS,
    ellipsisChars = Number.POSITIVE_INFINITY,
    width,
    height,
    reservedBoxes = [],
    desktop = false,
  } = options;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const segments: Segment[] = [];
  for (const e of edges) {
    const from = byId.get(e.source);
    const to = byId.get(e.target);
    if (from && to) {
      segments.push([
        [from.x, from.y],
        [to.x, to.y],
      ]);
    }
  }
  return {
    nodes,
    hulls,
    variant,
    phone,
    desktop,
    alwaysShowIds,
    fontPx,
    minVisibleChars,
    ellipsisChars,
    width,
    height,
    reservedBoxes,
    maxGap: desktop ? MAX_GAP_DESKTOP_PX : MAX_GAP_PX,
    cell: phone ? CELL_PHONE_PX : desktop ? CELL_WIDE_PX : CELL_DEFAULT_PX,
    segments,
    ranked: nodes.toSorted(byViews),
    placements: new Map<number, LabelBox | null>(nodes.map((n) => [n.id, null])),
    placedBoxes: [...reservedBoxes],
    placedLeaders: [],
    usedCells: new Set<string>(),
    wholeRecipes: new Map(),
  };
}

/**
 * Lists the ways to write a name, longest first: the whole name, the whole name on two lines for a related-graph title longer than LINE_MAX_CHARS that has a break, then each shorter cut.
 * A cut ends at a space; only a title with no such cut within reach is cut inside a word.
 * Callers prefer earlier entries, so a name is cut only when a longer wording has no room or costs more.
 */
function wordingsFor(
  run: Run,
  node: LaidOutNode,
  cut = true,
  minChars = MIN_CUT_CHARS,
  minVisible = run.minVisibleChars,
): Wording[] {
  const seen = new Set<string>();
  const out: Wording[] = [];
  const longest = Math.min(node.title.length, run.ellipsisChars);
  const lengths = cut
    ? Array.from({ length: Math.max(1, longest - minChars + 1) }, (_, i) => longest - i)
    : [longest];
  for (const max of lengths) {
    const text = ellipsize(node.title, max);
    if (seen.has(text)) {
      continue;
    }
    seen.add(text);
    // A start such as "East..." names nothing, so this wording is dropped.
    if (text !== node.title && visibleStart(text).length < minVisible) {
      continue;
    }
    const boxW = boxWidthFor(measureTextWidth(text, run.fontPx));
    out.push({ text, fullText: text === node.title ? undefined : node.title, boxW });
  }
  // A cut ends at a space. Only a title with no such cut within reach is cut inside a word.
  const atSpace = out.filter((w) => !w.fullText || !endsInsideWord(node.title, w.text));
  if (atSpace.some((w) => w.fullText)) {
    out.splice(0, out.length, ...atSpace);
  }
  const whole = out[0];
  const lines =
    run.variant === "related" && whole?.text === node.title && node.title.length > LINE_MAX_CHARS
      ? breakIntoTwoLines(node.title)
      : null;
  if (lines) {
    // Right after the whole name on one line: whole on two lines comes before any cut.
    out.splice(1, 0, {
      text: node.title,
      lines,
      boxH: TWO_LINE_BOX_HEIGHT,
      boxW: boxWidthFor(
        Math.max(measureTextWidth(lines[0], run.fontPx), measureTextWidth(lines[1], run.fontPx)),
      ),
    });
  }
  if (out.length === 0) {
    // Every cut was shorter than the minimum, so cut after the first word that reaches it.
    const stop = node.title.indexOf(" ", minVisible);
    const text = stop === -1 ? node.title : `${node.title.slice(0, stop)}...`;
    out.push({
      text,
      fullText: text === node.title ? undefined : node.title,
      boxW: boxWidthFor(measureTextWidth(text, run.fontPx)),
    });
  }
  const fitting = out.filter((v) => v.boxW <= run.width * WIDEST_NAME_SHARE);
  return fitting.length > 0 ? fitting : [out[out.length - 1]!];
}

/**
 * Returns true when the leader would cross another name, pass through another dot or cross a placed leader, or when the name sits on a placed leader.
 * Every rule set applies this check.
 */
function leaderBlocked(
  run: Run,
  box: LabelBox,
  node: LaidOutNode,
  leader: LabelBox["leader"],
): boolean {
  const tight = inflate(glyphsOf(box), LINE_CLEARANCE_PX);
  if (run.placedLeaders.some(([a, b]) => segmentHitsRect(a, b, tight))) {
    return true;
  }
  if (!leader) {
    return false;
  }
  const from: Point = [leader.x1, leader.y1];
  const to: Point = [leader.x2, leader.y2];
  if (
    run.placedBoxes.some(
      (other) =>
        other.id !== node.id &&
        segmentHitsRect(from, to, inflate(glyphsOf(other), LEADER_CLEARANCE_PX)),
    )
  ) {
    return true;
  }
  if (
    run.nodes.some(
      (other) =>
        other.id !== node.id &&
        pointSegmentDistance(other.x, other.y, from, to) < other.radius + LEADER_CLEARANCE_PX,
    )
  ) {
    return true;
  }
  return run.placedLeaders.some(([a, b]) => segmentsCross(from, to, a, b));
}

function insideFrame(run: Run, glyphs: Rect): boolean {
  return (
    glyphs.x >= FRAME_MARGIN_PX &&
    glyphs.y >= FRAME_MARGIN_PX &&
    glyphs.x + glyphs.width <= run.width - FRAME_MARGIN_PX &&
    glyphs.y + glyphs.height <= run.height - FRAME_MARGIN_PX
  );
}

/** Returns true when the box is inside the frame and clear of what `rules` forbids; `beside` says it stands beside its dot, not on a leader. */
function isFree(
  run: Run,
  box: LabelBox,
  node: LaidOutNode,
  rules: Rules,
  beside: boolean,
): boolean {
  const glyphs = glyphsOf(box);
  const tight = inflate(glyphs, LINE_CLEARANCE_PX);
  if (!insideFrame(run, glyphs)) {
    return false;
  }
  if (run.placedBoxes.some((other) => boxesOverlap(box, other))) {
    return false;
  }
  if (leaderBlocked(run, box, node, beside ? undefined : leaderFor(box, node))) {
    return false;
  }
  const own = boxCircleDistance(glyphs, node);
  for (const other of run.nodes) {
    if (other.id === node.id) {
      continue;
    }
    if (boxCircleDistance(box, other) < 1) {
      return false;
    }
    // Beside its dot a name must be nearer to its own dot than to any other, or it reads as the
    // other's.
    if (beside && boxCircleDistance(glyphs, other) < own + OWN_DOT_MARGIN_PX) {
      return false;
    }
  }
  if (rules.edges && run.segments.some(([a, b]) => segmentHitsRect(a, b, tight))) {
    return false;
  }
  for (const hull of run.hulls) {
    if (hull.cluster === node.cluster) {
      if (rules.ownOutline && boxCrossesOutline(tight, hull)) {
        return false;
      }
    } else if (rules.foreignOutlines && boxTouchesHull(tight, hull)) {
      return false;
    }
  }
  return true;
}

/** Counts the edges and the group outlines that run under a box's text. */
function countUnder(run: Run, box: LabelBox): { lines: number; outlines: number } {
  const tight = inflate(glyphsOf(box), LINE_CLEARANCE_PX);
  return {
    lines: run.segments.filter(([a, b]) => segmentHitsRect(a, b, tight)).length,
    outlines: run.hulls.filter((h) => boxCrossesOutline(tight, h)).length,
  };
}

/** Returns the eight anchors in the order a node tries them: away from the frame's centre first. */
function anchorOrder(run: Run, node: LaidOutNode): Anchor[] {
  const awayX: "right" | "left" = node.x >= run.width / 2 ? "right" : "left";
  const awayY: "above" | "below" = node.y >= run.height / 2 ? "below" : "above";
  const primary: Anchor = `${awayY}-${awayX}`;
  return [
    awayX,
    awayY,
    awayX === "right" ? "left" : "right",
    awayY === "below" ? "above" : "below",
    primary,
    ...ALL_DIAGONALS.filter((d) => d !== primary),
  ];
}

/** Returns the finer directions around a node, in radians, the ones pointing away from the frame's centre first. */
function fineAngles(run: Run, node: LaidOutNode): number[] {
  const away = Math.atan2(node.y - run.height / 2, node.x - run.width / 2);
  return Array.from(
    { length: FINE_DIRECTIONS },
    (_, k) => (k / FINE_DIRECTIONS) * 2 * Math.PI - Math.PI,
  )
    .map((angle) => ({
      angle,
      off: Math.abs(Math.atan2(Math.sin(angle - away), Math.cos(angle - away))),
    }))
    .toSorted((a, b) => a.off - b.off)
    .map((a) => a.angle);
}

/** Returns where the box of a wording could stand around a node at one ring: the eight anchors, then the finer directions when `angles` is given. */
function candidateSpots(
  run: Run,
  node: LaidOutNode,
  wording: Wording,
  gap: number,
  order: Anchor[],
  angles: number[] | null,
): Array<Pick<LabelBox, "x" | "y" | "textX" | "textAnchor">> {
  const wordingH = wording.boxH ?? LINE_BOX_HEIGHT;
  const spots: Array<Pick<LabelBox, "x" | "y" | "textX" | "textAnchor">> = order.map((anchor) => {
    const { bx, by, textX, textAnchor } = anchorPosition(
      anchor,
      node.x,
      node.y,
      node.radius,
      gap,
      wording.boxW,
      wordingH - LINE_BOX_HEIGHT,
    );
    if (wording.lines && textAnchor === "middle") {
      // A two-line name centred over or under a dot near the frame's edge slides inward, to stay
      // inside.
      const slid = Math.min(
        Math.max(bx, FRAME_MARGIN_PX - CENTRED_INSET_PX),
        run.width - wording.boxW + CENTRED_INSET_PX - FRAME_MARGIN_PX,
      );
      return { x: slid, y: by, textX: slid + wording.boxW / 2, textAnchor };
    }
    return { x: bx, y: by, textX, textAnchor };
  });
  if (angles) {
    // In between the 8 spots: the box stands off the dot's edge along a finer set of directions.
    for (const angle of angles) {
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);
      const px = node.x + dx * (node.radius + gap);
      const py = node.y + dy * (node.radius + gap);
      spots.push({
        x: px - wording.boxW / 2 + (dx * wording.boxW) / 2,
        y: py - wordingH / 2 + (dy * wordingH) / 2,
      });
    }
  }
  return spots;
}

/**
 * Searches the wordings, rings and spots for a free one and returns the first, or with `cheapest` the lowest priced spot of the first wording that has any.
 * Rings are tried in the order given, and `only` limits the search to given wordings.
 */
function searchScored(
  run: Run,
  node: LaidOutNode,
  rules: Rules,
  rings: number[],
  fine: boolean,
  cut = true,
  only?: Wording[],
  cheapest = false,
): Scored | null {
  const found: { box: LabelBox | null; cost: number; outline: boolean } = {
    box: null,
    cost: Number.POSITIVE_INFINITY,
    outline: false,
  };
  const order = anchorOrder(run, node);
  const angles = fineAngles(run, node);
  for (const wording of only ?? wordingsFor(run, node, cut)) {
    const wordingH = wording.boxH ?? LINE_BOX_HEIGHT;
    for (const gap of rings) {
      const spots = candidateSpots(
        run,
        node,
        wording,
        gap,
        order,
        fine && gap > RING_BESIDE_PX ? angles : null,
      );
      for (const spot of spots) {
        const box: LabelBox = {
          id: node.id,
          width: wording.boxW,
          height: wordingH,
          text: wording.text,
          fullText: wording.fullText,
          lines: wording.lines,
          ...spot,
        };
        if (
          boxCircleDistance(glyphsOf(box), node) <= run.maxGap &&
          isFree(run, box, node, rules, gap === RING_BESIDE_PX)
        ) {
          const placed = gap === RING_BESIDE_PX ? box : { ...box, leader: leaderFor(box, node) };
          if (!cheapest) {
            return { box: placed, cost: 0, outline: false };
          }
          // Of the spots that pass, the lowest price wins: the lines and outlines under the name
          // plus the ring's leader price. The first spot found breaks a tie.
          const under = countUnder(run, box);
          const cost = under.lines * LINE_COST + under.outlines * OUTLINE_COST + ringCost(gap);
          if (cost < found.cost) {
            found.box = placed;
            found.cost = cost;
            found.outline = under.outlines > 0;
          }
        }
      }
      if (found.box && found.cost === 0) {
        return { box: found.box, cost: 0, outline: false };
      }
    }
    if (found.box) {
      return { box: found.box, cost: found.cost, outline: found.outline };
    }
  }
  return null;
}

function search(
  run: Run,
  node: LaidOutNode,
  rules: Rules,
  rings: number[],
  fine: boolean,
  cut = true,
  only?: Wording[],
): LabelBox | null {
  return searchScored(run, node, rules, rings, fine, cut, only)?.box ?? null;
}

/** Counts the spots around a dot that are still free for its full name, given the names already placed. The dot with the fewest chooses next. */
function cleanSpots(run: Run, node: LaidOutNode, rules: Rules = STRICT): number {
  let count = 0;
  const text = wordingsFor(run, node)[0]!;
  const wordingH = text.boxH ?? LINE_BOX_HEIGHT;
  for (const gap of [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX]) {
    for (let k = 0; k < FINE_DIRECTIONS; k += 1) {
      const angle = (k / FINE_DIRECTIONS) * 2 * Math.PI;
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);
      const px = node.x + dx * (node.radius + gap);
      const py = node.y + dy * (node.radius + gap);
      const box: LabelBox = {
        id: node.id,
        x: px - text.boxW / 2 + (dx * text.boxW) / 2,
        y: py - wordingH / 2 + (dy * wordingH) / 2,
        width: text.boxW,
        height: wordingH,
        text: text.text,
      };
      if (isFree(run, box, node, rules, false)) {
        count += 1;
      }
    }
  }
  return count;
}

/**
 * Finds the cheapest spot for a name that has none: clear of the frame, the reserved boxes, placed leaders and every other name.
 * The price counts the dots, lines and outlines under the name, and adds small prices for a farther ring and for a shorter wording, down to a short start.
 * With no such spot the name is left out, so nothing is printed over another name.
 */
function bestEffort(run: Run, node: LaidOutNode): LabelBox | null {
  let best: { box: LabelBox; cost: number } | null = null;
  const anchors: Anchor[] = ["right", "left", "above", "below", ...ALL_DIAGONALS];
  for (const [index, text] of wordingsFor(
    run,
    node,
    true,
    MIN_CUT_CHARS_LAST_RESORT,
    MIN_VISIBLE_CHARS_LAST_RESORT,
  ).entries()) {
    if (text.lines) {
      continue;
    }
    for (const gap of [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX]) {
      for (const anchor of anchors) {
        const { bx, by, textX, textAnchor } = anchorPosition(
          anchor,
          node.x,
          node.y,
          node.radius,
          gap,
          text.boxW,
        );
        const box: LabelBox = {
          id: node.id,
          x: bx,
          y: by,
          width: text.boxW,
          height: LINE_BOX_HEIGHT,
          text: text.text,
          fullText: text.fullText,
          textX,
          textAnchor,
        };
        if (!insideFrame(run, glyphsOf(box))) {
          continue;
        }
        if (boxCircleDistance(glyphsOf(box), node) > run.maxGap) {
          continue;
        }
        const placed = gap === RING_BESIDE_PX ? box : { ...box, leader: leaderFor(box, node) };
        if (
          leaderBlocked(run, box, node, placed.leader) ||
          run.placedBoxes.some((o) => boxesOverlap(box, o))
        ) {
          continue;
        }
        const dotsUnder = run.nodes.filter(
          (o) => o.id !== node.id && boxCircleDistance(box, o) < 1,
        ).length;
        const under = countUnder(run, box);
        const cost =
          dotsUnder * DOT_UNDER_COST +
          under.lines * LINE_COST +
          under.outlines * OUTLINE_COST +
          gap / RING_FAR_PX +
          index * WORDING_STEP_COST;
        if (best == null || cost < best.cost) {
          best = { box: placed, cost };
        }
      }
    }
  }
  return best?.box ?? null;
}

/**
 * Places a name on the related variant by price: the wording with the lowest total of its cheapest spot and its own price wins.
 * Returns null when no wording has a free spot.
 */
function placePriced(run: Run, node: LaidOutNode, cut: boolean, rings: number[]): LabelBox | null {
  // A name keeps its whole text unless a cut is the only way to clear several lines.
  // A line that remains is hidden behind the halo, the outline drawn around the text; dots and
  // other names stay forbidden.
  let best: { box: LabelBox; cost: number } | null = null;
  const cutTries: Array<{ box: LabelBox; found: number }> = [];
  for (const wording of wordingsFor(run, node, cut)) {
    const penalty = wording.fullText
      ? CUT_COST + CUT_COST_PER_CHAR * (node.title.length - wording.text.length)
      : wording.lines
        ? TWO_LINE_COST
        : 0;
    if (best != null && penalty >= best.cost) {
      break;
    }
    const found = searchScored(run, node, PRICED, rings, true, true, [wording], true);
    if (found && wording.fullText) {
      cutTries.push({ box: found.box, found: found.cost });
    }
    if (found && (best == null || found.cost + penalty < best.cost)) {
      // Only a name standing on a group outline is flagged as relaxed: a line under a name is
      // hidden behind the halo.
      best = {
        box: found.outline ? { ...found.box, relaxed: 1 } : found.box,
        cost: found.cost + penalty,
      };
    }
    if (best != null && best.cost === 0) {
      break;
    }
  }
  if (best?.box.fullText) {
    // A cut name is swapped for a longer cut when that cut's spot costs at most STUB_EXTRA_LINES
    // lines' worth more.
    const floor = cutTries.find((t) => t.box.text === best!.box.text)?.found ?? 0;
    const longer = cutTries.find(
      (t) =>
        visibleStart(t.box.text).length <= STUB_MAX_CHARS &&
        t.box.text.length > best!.box.text.length &&
        t.found <= floor + STUB_EXTRA_LINES * LINE_COST,
    );
    if (longer) {
      best = { box: longer.box, cost: best.cost };
    }
  }
  return best?.box ?? null;
}

/**
 * Places a name that must be named. The related variant first takes the cheapest priced spot.
 * Both variants then relax MUST_RULES in turn, and the related variant ends with bestEffort when a cut is allowed.
 */
function placeMust(run: Run, node: LaidOutNode, cut: boolean): LabelBox | null {
  const rings =
    run.variant === "related" && run.desktop
      ? [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX, RING_OUTER_PX]
      : [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX];
  if (run.variant === "related") {
    const priced = placePriced(run, node, cut, rings);
    if (priced) {
      return priced;
    }
  }
  for (const [level, rules] of MUST_RULES.entries()) {
    const box = search(run, node, rules, rings, true, cut);
    if (box) {
      return level === 0 ? box : { ...box, relaxed: level };
    }
  }
  if (run.variant === "index" || !cut) {
    // The index variant drops a name that finds no free spot rather than print it over another name
    // or a dot. A whole-name retry has no last resort either.
    return null;
  }
  const box = bestEffort(run, node);
  return box ? { ...box, relaxed: MUST_RULES.length } : null;
}

/** Places a name whole by the recipe it was first placed with, or returns null when no whole spot is free. */
function placeWhole(run: Run, node: LaidOutNode): LabelBox | null {
  const recipe = run.wholeRecipes.get(node.id);
  if (!recipe) {
    return null;
  }
  return recipe === "must"
    ? placeMust(run, node, false)
    : search(run, node, STRICT, recipe.rings, recipe.fine, false);
}

/** Rebuilds the boxes and leaders every name must keep off from the names placed so far. */
function rebuildObstacles(run: Run): void {
  const shown = [...run.placements.values()].filter((b): b is LabelBox => b != null);
  run.placedBoxes = [...run.reservedBoxes, ...shown];
  run.placedLeaders = shown.flatMap((b) =>
    b.leader
      ? [
          [
            [b.leader.x1, b.leader.y1],
            [b.leader.x2, b.leader.y2],
          ] as Segment,
        ]
      : [],
  );
}

/** Sets or clears one name and refreshes the boxes and leaders later placements keep off. */
function setPlacement(run: Run, id: number, box: LabelBox | null): void {
  run.placements.set(id, box);
  rebuildObstacles(run);
}

/** Returns the key of the grid cell a dot stands in. */
function cellOf(run: Run, n: LaidOutNode): string {
  return `${Math.floor(n.x / run.cell)},${Math.floor(n.y / run.cell)}`;
}

/** Records a name as placed and adds its box, leader and grid cell to what later names keep off. */
function commit(run: Run, node: LaidOutNode, box: LabelBox): void {
  run.placements.set(node.id, box);
  run.placedBoxes.push(box);
  if (box.leader) {
    run.placedLeaders.push([
      [box.leader.x1, box.leader.y1],
      [box.leader.x2, box.leader.y2],
    ]);
  }
  run.usedCells.add(cellOf(run, node));
}

/**
 * A cut name whose visible text is the start of another shown name's whole title reads as that name ("2026 Asian Games..." beside "2026 Asian Games").
 * The cut one is shown whole where a spot is free; failing that, the lower-ranked of the two is dropped.
 */
function resolvePrefixMatches(run: Run): void {
  const rank = new Map(
    [
      ...run.nodes.filter((n) => run.alwaysShowIds.has(n.id)),
      ...run.ranked.filter((n) => !run.alwaysShowIds.has(n.id)),
    ].map((n, i) => [n.id, i]),
  );
  for (let pass = 0; pass < run.nodes.length; pass += 1) {
    let resolved = false;
    for (const [id, box] of run.placements) {
      if (!box?.fullText) {
        continue;
      }
      const stub = visibleStart(box.text);
      const match = [...run.placements.values()].find(
        (o): o is LabelBox => o != null && o.id !== id && fullOf(o).startsWith(stub),
      );
      if (!match) {
        continue;
      }
      setPlacement(run, id, null);
      const node = run.nodes.find((n) => n.id === id);
      const whole = node ? placeWhole(run, node) : null;
      if (whole) {
        setPlacement(run, id, whole);
      } else if ((rank.get(id) ?? 0) < (rank.get(match.id) ?? 0)) {
        setPlacement(run, id, box);
        setPlacement(run, match.id, null);
      }
      resolved = true;
      break;
    }
    if (!resolved) {
      break;
    }
  }
}

/**
 * The related variant aims to name every dot, so a name that ended up cut or unplaced gets one more try.
 * Another name is lifted out, this one is placed with a longer wording, and the other is then placed no shorter than it was.
 * The swap is kept only when both succeed.
 */
function repairCutNames(run: Run): void {
  for (const node of run.ranked) {
    const own = run.placements.get(node.id);
    if (own && !own.fullText) {
      continue;
    }
    for (const other of run.ranked) {
      const before = run.placements.get(other.id);
      if (other.id === node.id || !before || run.alwaysShowIds.has(other.id)) {
        continue;
      }
      setPlacement(run, other.id, null);
      setPlacement(run, node.id, null);
      const longer = placeMust(run, node, true);
      if (longer && longer.text.length > keptLength(own)) {
        setPlacement(run, node.id, longer);
        const again = placeMust(run, other, true);
        if (
          again &&
          keptLength(again) >= keptLength(before) &&
          (again.fullText == null || before.fullText != null)
        ) {
          setPlacement(run, other.id, again);
          run.wholeRecipes.set(node.id, "must");
          break;
        }
      }
      setPlacement(run, node.id, own ?? null);
      setPlacement(run, other.id, before);
    }
  }
}

/**
 * On the related variant, adds a leader to a name beside its dot when another dot is less than NEIGHBOUR_DOT_MARGIN_PX farther from it than its own.
 * The leader is skipped when leaderBlocked says it would cross a name, a dot or another leader.
 */
function joinCrowdedNames(run: Run): void {
  if (run.variant !== "related") {
    return;
  }
  for (const node of run.nodes) {
    const box = run.placements.get(node.id);
    if (!box || box.leader) {
      continue;
    }
    const glyphs = glyphsOf(box);
    const own = boxCircleDistance(glyphs, node);
    const crowded = run.nodes.some(
      (o) => o.id !== node.id && boxCircleDistance(glyphs, o) < own + NEIGHBOUR_DOT_MARGIN_PX,
    );
    if (!crowded) {
      continue;
    }
    const leader = leaderFor(box, node);
    if (!leaderBlocked(run, box, node, leader)) {
      setPlacement(run, node.id, { ...box, leader });
    }
  }
}

/** Places every dot once, seeds first. The next dot is the highest-ranked, or with `fewestSpotsFirst` the one with the fewest free spots for its whole name. */
function placeAll(
  run: Run,
  seeds: LaidOutNode[],
  others: LaidOutNode[],
  fewestSpotsFirst: boolean,
) {
  for (const n of run.nodes) {
    run.placements.set(n.id, null);
  }
  rebuildObstacles(run);
  const waiting = [...seeds, ...others];
  let pinned = seeds.length;
  while (waiting.length > 0) {
    let pick = 0;
    if (pinned > 0) {
      pinned -= 1;
    } else if (fewestSpotsFirst) {
      let fewest = Number.POSITIVE_INFINITY;
      for (const [i, candidate] of waiting.entries()) {
        const spots = cleanSpots(run, candidate, PRICED);
        if (spots < fewest) {
          fewest = spots;
          pick = i;
        }
      }
    }
    const node = waiting.splice(pick, 1)[0]!;
    const box = placeMust(run, node, true);
    if (box) {
      commit(run, node, box);
      run.wholeRecipes.set(node.id, "must");
    }
  }
  repairCutNames(run);
  resolvePrefixMatches(run);
}

/** Ranks a layout by its number of unnamed dots, then of cut names under minVisibleChars, then of cut names. The layout with the lower list at the first difference wins. */
function scoreOf(run: Run): number[] {
  const boxes = [...run.placements.values()];
  return [
    boxes.filter((b) => b == null).length,
    boxes.filter((b) => b?.fullText && visibleStart(b.text).length < run.minVisibleChars).length,
    boxes.filter((b) => b?.fullText).length,
  ];
}

/** Places the related variant: every dot is placed twice, by rank and by fewest free spots, and the better layout is kept. */
function placeRelated(run: Run): void {
  const seeds = run.nodes
    .filter((n) => run.alwaysShowIds.has(n.id))
    .toSorted((a, b) => a.id - b.id);
  const others = run.ranked.filter((n) => !run.alwaysShowIds.has(n.id));
  let best: { placed: Array<[number, LabelBox | null]>; score: number[] } | null = null;
  for (const fewestSpotsFirst of [false, true]) {
    placeAll(run, seeds, others, fewestSpotsFirst);
    const now = scoreOf(run);
    const first = best == null ? -1 : now.findIndex((v, i) => v !== best!.score[i]);
    if (best == null || (first !== -1 && now[first]! < best.score[first]!)) {
      best = { placed: [...run.placements.entries()], score: now };
    }
  }
  for (const [id, box] of best!.placed) {
    run.placements.set(id, box);
  }
  rebuildObstacles(run);
}

/** Returns the index variant's tiers in the order they are placed. */
function indexTiers(run: Run): Tier[] {
  const radius = run.phone ? ISOLATED_RADIUS_PHONE_PX : ISOLATED_RADIUS_DEFAULT_PX;
  const isolated = isolatedIds(run.nodes, radius);
  const must = new Set([
    ...run.ranked.slice(0, ALWAYS_NAMED).map((n) => n.id),
    ...run.alwaysShowIds,
  ]);
  const representatives = new Set<number>();
  for (const hull of run.hulls) {
    const top = run.ranked.find((n) => n.cluster === hull.cluster);
    if (top) {
      representatives.add(top.id);
    }
  }
  const tiers: Tier[] = [
    {
      ids: run.ranked.filter((n) => must.has(n.id)),
      rules: [],
      rings: [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX],
      oneInCell: false,
      fine: true,
      must: true,
    },
    {
      ids: run.ranked.filter((n) => isolated.has(n.id)),
      rules: [STRICT],
      rings: [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX],
      oneInCell: false,
      fine: true,
      must: false,
    },
    {
      ids: run.ranked.filter((n) => representatives.has(n.id)),
      rules: [STRICT],
      rings: [RING_BESIDE_PX, RING_NEAR_PX],
      oneInCell: false,
      fine: false,
      must: false,
    },
    {
      ids: run.ranked,
      rules: [STRICT],
      rings: [RING_BESIDE_PX, RING_NEAR_PX],
      oneInCell: true,
      fine: false,
      must: false,
    },
  ];
  if (run.desktop) {
    // Every tier below the first also gets the outer ring and the finer directions, tried ring by
    // ring after the eight anchors of each ring.
    for (const tier of tiers.slice(1)) {
      tier.rings = [RING_BESIDE_PX, RING_NEAR_PX, RING_FAR_PX, RING_OUTER_PX];
      tier.fine = true;
    }
  }
  return tiers;
}

/** Places every dot of a tier by `placeMust`; the dot with the fewest clean spots left chooses next, re-counted after every name placed. */
function placeMustTier(run: Run, tier: Tier, taken: Set<number>): void {
  const waiting = [...tier.ids];
  while (waiting.length > 0) {
    let pick = 0;
    let fewest = Number.POSITIVE_INFINITY;
    for (const [i, candidate] of waiting.entries()) {
      const spots = cleanSpots(run, candidate);
      if (spots < fewest) {
        fewest = spots;
        pick = i;
      }
    }
    const node = waiting.splice(pick, 1)[0]!;
    const box = placeMust(run, node, true);
    if (box) {
      taken.add(node.id);
      commit(run, node, box);
      run.wholeRecipes.set(node.id, "must");
    }
  }
}

/** Places the dots of a tier one by one, each under the tier's rules in turn; a dot that finds no spot stays unnamed. */
function placeSearchTier(run: Run, tier: Tier, taken: Set<number>): void {
  for (const node of tier.ids) {
    if (taken.has(node.id) || (tier.oneInCell && run.usedCells.has(cellOf(run, node)))) {
      continue;
    }
    let box: LabelBox | null = null;
    for (const [level, rules] of tier.rules.entries()) {
      box = search(run, node, rules, tier.rings, tier.fine);
      if (box) {
        box = level === 0 ? box : { ...box, relaxed: level };
        break;
      }
    }
    if (box) {
      taken.add(node.id);
      commit(run, node, box);
      run.wholeRecipes.set(node.id, { rings: tier.rings, fine: tier.fine });
    }
  }
}

/** Places the index variant tier by tier. */
function placeIndex(run: Run): void {
  const taken = new Set<number>();
  for (const tier of indexTiers(run)) {
    if (tier.must) {
      placeMustTier(run, tier, taken);
    } else {
      placeSearchTier(run, tier, taken);
    }
  }
}

/** Decides which dots are named and where, returning a map from every node id to its label box, or null for a dot left unnamed. */
export function computeLabelPlacements(
  nodes: LaidOutNode[],
  hulls: Hull[],
  options: LabelPlacementOptions,
): Map<number, LabelBox | null> {
  const run = createRun(nodes, hulls, options);
  if (run.variant === "related") {
    placeRelated(run);
  } else {
    placeIndex(run);
    resolvePrefixMatches(run);
  }
  joinCrowdedNames(run);
  return run.placements;
}
