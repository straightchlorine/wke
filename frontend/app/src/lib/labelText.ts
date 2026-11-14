import { GLYPH_LEFT_PX, LABEL_HALO_PAD, LABEL_LINE_HEIGHT, boxWidthFor } from "./labelGeometry";
import type { LabelBox } from "./labelGeometry";

/** A name's backing is the rectangle in the frame colour drawn behind it. It reaches this far past the glyphs on each side. */
const NAME_BACKING_PAD_PX = 3;
/** How far the backing's top sits below the box's top edge. */
const NAME_BACKING_TOP_PX = 4;
/** How much shorter than its label box the backing is. */
const NAME_BACKING_TRIM_PX = 2;

/** Returns the x where a label's text is drawn: its own origin, or `GLYPH_LEFT_PX` in from the box's left edge. */
export function textOriginX(box: LabelBox): number {
  return box.textX ?? box.x + GLYPH_LEFT_PX;
}

/** Returns the y of a label's text baseline: one `LABEL_HALO_PAD` above the box's bottom edge, and above the second line of a two-line name. */
export function textBaselineY(box: LabelBox): number {
  return box.y + box.height - LABEL_HALO_PAD - (box.lines ? LABEL_LINE_HEIGHT : 0);
}

/** Returns the x where a name's glyphs begin, whichever end of the text is anchored. */
export function nameLeft(box: LabelBox): number {
  const textWidth = box.width - boxWidthFor(0);
  const x = textOriginX(box);
  return box.textAnchor === "end"
    ? x - textWidth
    : box.textAnchor === "middle"
      ? x - textWidth / 2
      : x;
}

/** Returns the rectangle of the backing drawn behind a name that sits beside its dot, in the graph's px coordinates. */
export function nameBackingRect(box: LabelBox): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  return {
    x: nameLeft(box) - NAME_BACKING_PAD_PX,
    y: box.y + NAME_BACKING_TOP_PX,
    width: box.width - boxWidthFor(0) + 2 * NAME_BACKING_PAD_PX,
    height: box.height - NAME_BACKING_TRIM_PX,
  };
}
