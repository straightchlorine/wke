/** The padding between the plate frame's outer border and its inner border, on each side, in px. */
const FRAME_PADDING_PX = 3;

/**
 * Returns the width the plate frame takes from the graph inside it: on each side an outer border,
 * the padding and an inner border.
 */
export function plateFrameInsetPx(hairlinePx: number): number {
  return 2 * (FRAME_PADDING_PX + 2 * hairlinePx);
}

/** Reads the width of a 1px rule from the page's `--hairline` token, or 1 when the token is not set. */
export function readHairlinePx(): number {
  const value = Number.parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue("--hairline"),
  );
  return Number.isFinite(value) ? value : 1;
}
