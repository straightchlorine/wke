/**
 * Pure geometry for placing a tooltip next to its trigger. Every length is in screen px: the caller
 * converts CSS px by the root zoom before calling and back after.
 */

/** The sides of a box, as a DOMRect has them. */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** A point on the screen. */
export interface Point {
  x: number;
  y: number;
}

/** A place for the tooltip's top-left corner. `far` is false for the trigger's own spot and the spot under the anchor. */
export interface Spot extends Point {
  far: boolean;
}

/** The tooltip's size. */
export interface TipSize {
  width: number;
  height: number;
}

/** What bounds a placement: the horizontal limits, the viewport and the spacing. */
export interface PlacementLimits {
  /** The tooltip's left edge may not go below this. */
  minLeft: number;
  /** The tooltip's right edge may not go beyond this. */
  maxRight: number;
  viewportHeight: number;
  /** The least distance kept from the viewport's top and bottom edges. */
  inset: number;
  /** The distance between the trigger and a tooltip placed above or below it. */
  gap: number;
  /** The root zoom, which scales the fixed scroll limits below. */
  zoom: number;
}

/** What a tooltip keeps clear of, and the places it may move to. */
export interface TipClearance {
  /** The row the trigger sits in; the side spots hang off its edges. */
  anchor: Rect;
  /** The box whose top-right and bottom-right corners are fallback spots, and below which the `outside` spot is placed. */
  frame: Rect;
  /** Regions the tooltip must not cover. */
  avoid: Rect[];
  /** Points of an outline the tooltip must not cover. */
  points: Point[];
  /** Regions of other things on the page the tooltip should avoid when it can. */
  others?: Rect[];
  /** Outline points of those other things. */
  otherPoints?: Point[];
  /** Tries the spot beside the anchor, vertically centred on it, before the other spots. */
  besideFirst?: boolean;
  /**
   * A region below `frame` the tooltip may fall back to. When no spot is clear, the tooltip opens just under the frame, left-aligned with `anchor`, with an invisible bridge up to the anchor.
   * It does so only if it fits in this region and inside the horizontal limits.
   */
  outside?: Rect;
}

/** Covering a region by one px^2 costs 1; this many times more when the region is in `avoid`. */
export const AVOID_WEIGHT = 1000;
/** An outline point inside the tooltip costs as much as this many px^2 of covered region. */
export const OUTLINE_POINT_COST = 100;
/** A frame-corner spot sits this share of the viewport inset inside the frame. */
export const FRAME_CORNER_INSET_SHARE = 0.5;
/** The most the page may scroll to bring a tooltip that fell back under its frame into view. */
export const SCROLL_FOR_TIP_PX = 160;
/** The most of a frame's top the page may scroll away for that. */
export const MAX_FRAME_CUT_PX = 24;
// A scroll that falls this short of the one asked for still counts, for sub-pixel rounding.
const SCROLL_TOLERANCE_PX = 0.5;

/** The result of placing a tooltip by its trigger alone. */
export interface TriggerPlacement {
  x: number;
  y: number;
  /** Set when the tooltip is taller than the room on its side: it must scroll inside this height. */
  maxHeight: number | null;
}

/**
 * Places the tooltip above the trigger, or below it when above would clip and below has more room,
 * and keeps it inside the horizontal limits. A tooltip taller than the chosen side gets a `maxHeight`.
 */
export function placeByTrigger(
  button: Rect,
  tip: TipSize,
  limits: PlacementLimits,
): TriggerPlacement {
  const { minLeft, maxRight, viewportHeight, inset, gap } = limits;
  const roomAbove = button.top - gap - inset;
  const roomBelow = viewportHeight - inset - button.bottom - gap;
  let below = false;
  let height = tip.height;
  let maxHeight: number | null = null;
  if (height > roomAbove) {
    below = roomBelow > roomAbove;
    const room = below ? roomBelow : roomAbove;
    if (height > room) {
      height = Math.max(room, 0);
      maxHeight = height;
    }
  }
  return {
    x: Math.max(minLeft, Math.min(button.left, maxRight - tip.width)),
    y: below ? button.bottom + gap : button.top - gap - height,
    maxHeight,
  };
}

/** The part of `rect` the tooltip at `spot` covers, in px^2. */
function coveredArea(spot: Point, tip: TipSize, rect: Rect): number {
  const w = Math.min(spot.x + tip.width, rect.right) - Math.max(spot.x, rect.left);
  const h = Math.min(spot.y + tip.height, rect.bottom) - Math.max(spot.y, rect.top);
  return w > 0 && h > 0 ? w * h : 0;
}

function coveredCost(spot: Point, tip: TipSize, rects: Rect[], points: Point[]): number {
  const area = rects.reduce((sum, rect) => sum + coveredArea(spot, tip, rect), 0);
  const hit = points.filter(
    (pt) =>
      pt.x >= spot.x && pt.x <= spot.x + tip.width && pt.y >= spot.y && pt.y <= spot.y + tip.height,
  );
  return area + hit.length * OUTLINE_POINT_COST;
}

/** How much the tooltip at `spot` covers of what it should avoid. Zero means the spot is clear. */
export function overlapCost(spot: Point, tip: TipSize, clearance: TipClearance): number {
  const { avoid, points, others = [], otherPoints = [] } = clearance;
  return (
    coveredCost(spot, tip, avoid, points) * AVOID_WEIGHT +
    coveredCost(spot, tip, others, otherPoints)
  );
}

/**
 * The spots to try, in order: the trigger spot, then right of the anchor (its bottom and top
 * aligned), under the anchor, beside it on its line, above the anchor's right end, and the
 * top-right and bottom-right corners of the frame. `besideFirst` moves the side spot to the front.
 * Spots that leave the horizontal limits or the viewport are dropped.
 */
export function candidateSpots(
  triggerSpot: Point,
  tip: TipSize,
  clearance: TipClearance,
  limits: PlacementLimits,
): Spot[] {
  const { anchor, frame, besideFirst } = clearance;
  const { minLeft, maxRight, viewportHeight, inset, gap } = limits;
  const corner = inset * FRAME_CORNER_INSET_SHARE;
  const beside: Spot = {
    x: anchor.right + gap,
    y: (anchor.top + anchor.bottom) / 2 - tip.height / 2,
    far: true,
  };
  const spots: Spot[] = [
    ...(besideFirst ? [beside] : []),
    { ...triggerSpot, far: false },
    { x: anchor.right + gap, y: anchor.bottom - tip.height, far: true },
    { x: anchor.right + gap, y: anchor.top - tip.height, far: true },
    { x: triggerSpot.x, y: anchor.bottom + gap, far: false },
    ...(besideFirst ? [] : [beside]),
    { x: anchor.right - tip.width, y: anchor.top - gap - tip.height, far: true },
    { x: frame.right - corner - tip.width, y: frame.top + corner, far: true },
    { x: frame.right - corner - tip.width, y: frame.bottom - corner - tip.height, far: true },
  ];
  return spots.filter(
    (spot) =>
      spot.x >= minLeft &&
      spot.x + tip.width <= maxRight &&
      spot.y >= inset &&
      spot.y + tip.height <= viewportHeight - inset,
  );
}

/** The spot chosen among the candidates and how much it still covers. */
export interface ClearChoice {
  /** Null when no candidate fits the limits. */
  spot: Spot | null;
  /** Zero when the spot is clear; infinite when there is no spot. */
  overlap: number;
}

/** Takes the first candidate that covers nothing to avoid, else the one covering the least. */
export function chooseClearSpot(
  triggerSpot: Point,
  tip: TipSize,
  clearance: TipClearance,
  limits: PlacementLimits,
): ClearChoice {
  let spot: Spot | null = null;
  let overlap = Infinity;
  for (const candidate of candidateSpots(triggerSpot, tip, clearance, limits)) {
    const cost = overlapCost(candidate, tip, clearance);
    if (cost < overlap) {
      spot = candidate;
      overlap = cost;
    }
  }
  return { spot, overlap };
}

/** A spot just under the frame, and how far the page must scroll to show it. */
export interface UnderFramePlacement {
  spot: Spot;
  /** Zero when the spot is already in view. */
  scrollBy: number;
}

/**
 * Places the tooltip just under the frame, left-aligned with the anchor, when that fits the
 * `outside` region and the horizontal limits and needs at most `SCROLL_FOR_TIP_PX` of scrolling.
 * Returns null when it does not fit or `clearance.outside` is not set.
 */
export function placeUnderFrame(
  tip: TipSize,
  clearance: TipClearance,
  limits: PlacementLimits,
): UnderFramePlacement | null {
  const { anchor, frame, outside } = clearance;
  const { minLeft, maxRight, viewportHeight, inset, gap, zoom } = limits;
  if (!outside) {
    return null;
  }
  const spot: Spot = {
    x: Math.max(minLeft, Math.min(anchor.left, maxRight - tip.width)),
    y: frame.bottom + gap,
    far: true,
  };
  const bottom = spot.y + tip.height;
  const fits =
    spot.x + tip.width <= maxRight &&
    bottom <= outside.bottom &&
    bottom <= viewportHeight - inset + SCROLL_FOR_TIP_PX * zoom;
  if (!fits) {
    return null;
  }
  return { spot, scrollBy: Math.max(bottom - (viewportHeight - inset), 0) };
}

/**
 * Whether a scroll of `scrolled` px, made to scroll `wanted` px, brought the tooltip in without
 * pushing more than `MAX_FRAME_CUT_PX` of the frame's top (at `frameTop` before the scroll) off the
 * screen.
 */
export function scrollKeepsFrame(
  scrolled: number,
  wanted: number,
  frameTop: number,
  zoom: number,
): boolean {
  return (
    scrolled >= wanted - SCROLL_TOLERANCE_PX && frameTop - scrolled >= -MAX_FRAME_CUT_PX * zoom
  );
}

/** The invisible strip joining a tooltip under the frame to the anchor above it. */
export interface BridgeBox {
  /** Offset of the strip's left edge from the tooltip's left edge. */
  left: number;
  width: number;
  height: number;
}

/** The strip spanning the tooltip and the anchor, from the anchor's bottom down to the tooltip. */
export function bridgeBox(spot: Point, tipWidth: number, anchor: Rect): BridgeBox {
  const from = Math.min(spot.x, anchor.left);
  const to = Math.max(spot.x + tipWidth, anchor.right);
  return { left: from - spot.x, width: to - from, height: spot.y - anchor.bottom };
}
