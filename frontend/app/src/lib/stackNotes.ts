/** Minimum clear space between two stacked margin notes, in px. */
export const NOTE_GAP_PX = 12;

/**
 * Places margin notes at their wanted tops, pushing each down below the previous note, and pulls
 * the last one up to end inside the article when there is room above it.
 */
export function stackNotes(
  tops: number[],
  heights: number[],
  bottom: number,
  gap = NOTE_GAP_PX,
): number[] {
  const placed: number[] = [];
  let previousBottom = -Infinity;
  tops.forEach((top, index) => {
    const y = Math.max(top, previousBottom + gap);
    placed.push(y);
    previousBottom = y + (heights[index] ?? 0);
  });
  const last = placed.length - 1;
  const lastTop = placed[last];
  if (lastTop !== undefined) {
    const height = heights[last] ?? 0;
    const previousTop = placed[last - 1];
    const floor = previousTop === undefined ? 0 : previousTop + (heights[last - 1] ?? 0) + gap;
    if (lastTop + height > bottom) {
      placed[last] = Math.max(floor, bottom - height);
    }
  }
  return placed;
}
