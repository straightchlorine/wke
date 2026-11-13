import type { ExcludeBox, LayoutOptions } from "./graphLayout";
import type { LabelBox } from "./labelGeometry";
import type { LabelPlacementOptions } from "./labelLayout";
import { legendRect, type LegendSize } from "./plateLegend";

/**
 * The options that lay out and name a concept graph in its frame.
 * They depend only on the variant and the frame, so a test builds the same ones the page does.
 */

/** A frame narrower than this counts as a phone's when the caller does not say. */
const PHONE_WIDTH_PX = 700;
/** A frame this wide or wider is never taken for a square one: it has room for the landscape layout. */
const SPACIOUS_SQUARE_PX = 480;
/** How far apart a frame's width and height may be, as a share of the longer side, for the frame to count as square. */
const SQUARE_TOLERANCE = 0.05;
/** The width a stats chip takes in the frame's top-right corner, where it floats: room for its longest text plus its offset from the frame's right edge. */
const STATS_CHIP_BOX_WIDTH_PX = 204;
/** The height the stats chip takes in that corner: the chip itself plus its offset from the frame's top edge. */
const STATS_CHIP_BOX_HEIGHT_PX = 30;
/** A name keeps this far off the legend chip, so a leader's end and the outline drawn around the text stay clear of it too. */
const LEGEND_LABEL_CLEARANCE_PX = 3;
/** Padding of a group's outline around its dots, in px. */
const HULL_PAD_PX = 18;
/** The least distance from a dot's edge to the frame on the index graph, half a pixel over the layout's default so rounding in the browser cannot put a dot closer than that default. */
const INDEX_WALL_MARGIN_PX = 12.5;
/** The smallest and largest dot radius in px. A close-to-square frame holds more dots per unit area than a landscape one, so its dots are smaller. */
const SQUARE_RADIUS_RANGE_PX: [number, number] = [4, 11];
const LANDSCAPE_RADIUS_RANGE_PX: [number, number] = [5, 16];
/** Longest name, in characters, of a dot that has no permanent label, on a wide index graph and on the related graph. */
const WIDE_NAME_CHARS = 26;
/** Longest such name on an index graph drawn for a phone. */
const PHONE_NAME_CHARS = 18;
/** The related graph lets a name stand far off its dot, on a leader, once its frame is this wide. */
const RELATED_WIDE_FRAME_PX = 270;
/** A cut name keeps this many characters ahead of its ellipsis, on the related graph and on an index graph under the desktop layout, or is not cut. */
const MIN_CUT_NAME_CHARS = 18;

/** What decides how a graph is laid out and named in its frame. */
export interface PlateFrame {
  variant: "index" | "related";
  /** The drawing area's size in CSS px. */
  width: number;
  height: number;
  /** The caller's own phone decision; omitted, a frame under PHONE_WIDTH_PX wide counts as a phone's. */
  compact?: boolean;
  /** Forces or forbids the layout for a close-to-square frame; omitted, it is read from the frame's size. */
  squareFrame?: boolean;
  /** True when the viewport is wide enough for the stats chip to float over the index graph's frame, not sit above it. */
  chipOverlaysFrame: boolean;
  /** True when the viewport is narrower than the desktop layout. */
  underDesktop: boolean;
  /** The size of the legend chip drawn over the index graph's frame; null or omitted when there is none. */
  legendSize?: LegendSize | null;
}

export interface PlateLayoutOptions {
  /** The options for `computeLayout`. */
  layout: LayoutOptions;
  /** The options for `computeLabelPlacements`; the caller adds `edges`, `alwaysShowIds` and `fontsReady`. */
  labels: LabelPlacementOptions & { reservedBoxes: LabelBox[] };
  /** The longest name, in characters, of a dot that has no permanent label. */
  nameChars: number;
}

/** Returns the ids of the dots always named: the first node of the index graph, which the caller sorts by rank, and the seed of the related graph. */
export function guaranteedNameIds(
  variant: "index" | "related",
  nodes: Array<{ id: number; role?: "seed" | "related" }>,
): Set<number> {
  const ids = new Set<number>();
  if (variant === "index" && nodes[0]) {
    ids.add(nodes[0].id);
  }
  if (variant === "related") {
    for (const n of nodes) {
      if (n.role === "seed") {
        ids.add(n.id);
      }
    }
  }
  return ids;
}

/** Returns the layout and label options of a graph in its frame. */
export function plateLayoutOptions(frame: PlateFrame): PlateLayoutOptions {
  const { variant, width, height, compact, squareFrame, chipOverlaysFrame, underDesktop } = frame;
  const isPhone = compact ?? width < PHONE_WIDTH_PX;
  const isSquare =
    squareFrame ??
    (width < SPACIOUS_SQUARE_PX &&
      Math.abs(width - height) <= Math.max(width, height) * SQUARE_TOLERANCE);
  // Dots and names keep off the stats chip. The index graph has it over its frame from the viewport
  // width that fits it; the related graph has it unless it is drawn for a phone.
  const reserveChip = variant === "index" ? chipOverlaysFrame : !isPhone;
  const chip: LabelBox[] = reserveChip
    ? [
        {
          id: -1,
          x: Math.max(0, width - STATS_CHIP_BOX_WIDTH_PX),
          y: 0,
          width: Math.min(STATS_CHIP_BOX_WIDTH_PX, width),
          height: STATS_CHIP_BOX_HEIGHT_PX,
          text: "",
        },
      ]
    : [];
  // The legend chip sits over the index graph's bottom-left corner: dots and group outlines keep
  // off its rectangle, and names stay clear of it.
  const legend =
    variant === "index" && frame.legendSize ? legendRect(frame.legendSize, height) : null;
  const excludeBoxes: ExcludeBox[] = [...chip, ...(legend ? [{ ...legend, hull: true }] : [])];
  const reservedBoxes: LabelBox[] = [
    ...chip,
    ...(legend
      ? [
          {
            id: -2,
            x: legend.x - LEGEND_LABEL_CLEARANCE_PX,
            y: legend.y - LEGEND_LABEL_CLEARANCE_PX,
            width: legend.width + LEGEND_LABEL_CLEARANCE_PX * 2,
            height: legend.height + LEGEND_LABEL_CLEARANCE_PX * 2,
            text: "",
          },
        ]
      : []),
  ];
  // The related graph is drawn in a narrow column even on a desktop, so its names do not follow the
  // viewport. The index graph is drawn for a phone only on a viewport too narrow for the stats chip
  // to float over its frame.
  const phoneNames = variant === "index" && compact === undefined ? !chipOverlaysFrame : isPhone;
  return {
    layout: {
      width,
      height,
      excludeBoxes,
      squareFrame: isSquare,
      hullPad: HULL_PAD_PX,
      wallMargin: variant === "index" ? INDEX_WALL_MARGIN_PX : undefined,
      radiusRange: isSquare ? SQUARE_RADIUS_RANGE_PX : LANDSCAPE_RADIUS_RANGE_PX,
    },
    labels: {
      variant,
      phone: phoneNames,
      minVisibleChars: variant === "related" || underDesktop ? MIN_CUT_NAME_CHARS : undefined,
      width,
      height,
      reservedBoxes,
      desktop: variant === "index" ? !underDesktop && !phoneNames : width >= RELATED_WIDE_FRAME_PX,
    },
    nameChars: variant === "index" && phoneNames ? PHONE_NAME_CHARS : WIDE_NAME_CHARS,
  };
}
