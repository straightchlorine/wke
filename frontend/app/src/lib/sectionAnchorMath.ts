/**
 * Gap between the sticky bars and the landing line, the line where a heading comes to rest after a
 * jump.
 */
export const LANDING_GAP_PX = 16;

// A restore keeps the reader's depth into a section only if the section is at least this much
// taller than that depth.
// This is about one line of body text.
const SECTION_TAIL_LINE_PX = 28;

/** Where the reader was: a section heading and how far from the viewport top it sat. */
export interface SectionAnchor {
  /** Section element id, e.g. "s5". */
  id: string;
  /** Section number, 5 for "s5". */
  number: number;
  /** The heading's top edge relative to the viewport top, in px. */
  offset: number;
  /** Date.now() at capture. */
  at: number;
}

/**
 * Returns the index of the last heading top at or above the threshold (with 2 px of slack), else 0,
 * or -1 when there are no headings.
 */
export function pickAnchorIndex(tops: readonly number[], threshold: number): number {
  if (tops.length === 0) {
    return -1;
  }
  let picked = 0;
  tops.forEach((top, index) => {
    if (top <= threshold + 2) {
      picked = index;
    }
  });
  return picked;
}

/**
 * Returns the offset to scroll the restored heading to: its recorded offset, or `landing` when the
 * section shrank below how far the reader had scrolled into it.
 */
export function restoredOffset(offset: number, landing: number, sectionHeight: number): number {
  if (offset >= landing) {
    return offset;
  }
  const room = Math.max(0, sectionHeight - SECTION_TAIL_LINE_PX);
  return landing - offset > room ? landing : offset;
}
