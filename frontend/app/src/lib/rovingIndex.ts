/** Returns the item that gets focus after `key` from `current` among `count` items, or null when the key moves nothing. Arrow keys stop at the ends. */
export function nextRovingIndex(key: string, current: number, count: number): number | null {
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return Math.min(current + 1, count - 1);
    case "ArrowLeft":
    case "ArrowUp":
      return Math.max(current - 1, 0);
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}
