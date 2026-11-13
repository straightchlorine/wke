import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { nextRovingIndex } from "../rovingIndex";

/** True when a key event started inside the element that handles it, not in a portal child that React bubbles to it. */
export function keyStartedInside(event: KeyboardEvent): boolean {
  return event.target instanceof Node && event.currentTarget.contains(event.target);
}

/**
 * Keeps one of `count` items in the tab order and moves focus between them with the arrow keys,
 * Home and End. Items register through `itemRef` and report focus through `markFocused`, which
 * updates the tab order after a key move. `current` stays inside the item range when `count` shrinks.
 */
export function useRovingFocus(count: number) {
  const items = useRef<Array<HTMLElement | null>>([]);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const current = Math.min(focusedIndex, Math.max(count - 1, 0));

  return {
    /** The item that is in the tab order. */
    current,
    /** Returns the ref callback for the item at `index`. */
    itemRef: (index: number) => (el: HTMLElement | null) => {
      items.current[index] = el;
    },
    /** Records that the item at `index` has focus, so it takes the tab order. */
    markFocused: setFocusedIndex,
    /** Moves focus to the item that is in the tab order. */
    focusCurrent: () => items.current[current]?.focus(),
    /** Focuses the next item on an arrow key, Home or End pressed inside the handler's element. Returns true when it did. */
    moveOnKey: (event: KeyboardEvent): boolean => {
      if (!keyStartedInside(event) || count === 0) {
        return false;
      }
      const next = nextRovingIndex(event.key, current, count);
      if (next == null) {
        return false;
      }
      items.current[next]?.focus();
      return true;
    },
  };
}
