/**
 * Size and position of the legend chip, the small box of colour swatches in the bottom-left corner of
 * the graph's frame. `Plate` draws the chip and the graph keeps clear of it, so both read the numbers from here.
 */

export const LEGEND_SWATCH_PX = 12;
/** The chip's distance from the frame's outer edge. The caption chip uses the same distance when it floats over the frame's top-right corner. */
export const LEGEND_INSET_PX = 8;
/** What lies between the frame's outer edge and the drawing area: border, padding, inner border. */
export const PLATE_EDGE_PX = 5;
const GAP_FINE_PX = 12;
/** Gap under a coarse pointer, wide enough that neighbouring swatch hit areas do not overlap. */
const GAP_COARSE_PX = 32;
/** The chip's side padding. Under a coarse pointer the end swatches' hit areas reach past the chip's side edge but stay inside the frame. */
const PAD_X_FINE_PX = 6;
const PAD_X_COARSE_PX = 8;
/**
 * The chip's height. Under a coarse pointer each swatch's hit area overhangs the chip at the top and bottom.
 * The bottom overhang ends at the frame's outer edge.
 */
const HEIGHT_FINE_PX = 22;
const HEIGHT_COARSE_PX = 28;
/** The chip's border width on each side. The drawn border is the `--hairline` token, which stays within a fraction of a pixel of this. */
const BORDER_PX = 1;

export interface LegendSize {
  width: number;
  height: number;
}

/** Returns the legend chip's outer width and height in px for the given swatch count and pointer type. */
export function legendChipSize(count: number, coarse: boolean): LegendSize {
  const gap = coarse ? GAP_COARSE_PX : GAP_FINE_PX;
  const pad = coarse ? PAD_X_COARSE_PX : PAD_X_FINE_PX;
  return {
    width: 2 * (pad + BORDER_PX) + count * LEGEND_SWATCH_PX + Math.max(0, count - 1) * gap,
    height: coarse ? HEIGHT_COARSE_PX : HEIGHT_FINE_PX,
  };
}

/** Returns the legend chip's rectangle in the drawing area's coordinates, in the bottom-left corner and `LEGEND_INSET_PX` in from the frame's outer edge. */
export function legendRect(chip: LegendSize, height: number) {
  const inset = LEGEND_INSET_PX - PLATE_EDGE_PX;
  return {
    x: inset,
    y: height - inset - chip.height,
    width: chip.width,
    height: chip.height,
  };
}
