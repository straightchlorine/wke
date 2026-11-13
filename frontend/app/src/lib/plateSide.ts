/**
 * Home's plate is the framed graph. Its board is the box under the frame that describes the dot
 * the pointer is on.
 */

/** The board's outer height in px, the same in every state and at every width. */
export const PLATE_BOARD_PX = 154;
/** The gap between the plate frame and its board, in px. */
const BOARD_GAP_PX = 8;
/** Space left below the board so it never touches the viewport's bottom edge. */
const CLEARANCE_PX = 12;
/** The least side of the plate frame in px, however short the window. */
const MIN_SIDE_PX = 320;
/** The most the plate may span on screen, in viewport px, so it does not stretch across the whole column on a very wide display. */
const MAX_SIDE_SCREEN_PX = 1000;

/**
 * Returns the side, in whole px, of Home's square plate frame on a desktop layout.
 *
 * It is the column's width, shrunk to fit the frame and the board under it in `roomPx`, and capped at
 * `MAX_SIDE_SCREEN_PX` on screen, but never below `MIN_SIDE_PX`. `roomPx` is the height from the plate's
 * top edge to the viewport's bottom in layout px, and `zoom` is the root zoom (`--ui-zoom`).
 */
export function plateSide(columnPx: number, roomPx: number, zoom = 1): number {
  const fits = roomPx - BOARD_GAP_PX - PLATE_BOARD_PX - CLEARANCE_PX;
  const cap = MAX_SIDE_SCREEN_PX / zoom;
  return Math.max(MIN_SIDE_PX, Math.floor(Math.min(columnPx, fits, cap)));
}
