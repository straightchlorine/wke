import { useState } from "react";

const PAUSE_STORAGE_KEY = "wke-paused";

/** Returns whether the reader left the feed paused on an earlier visit, or false when storage cannot be read. */
function readStoredPaused(): boolean {
  try {
    return window.localStorage.getItem(PAUSE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeStoredPaused(paused: boolean) {
  try {
    window.localStorage.setItem(PAUSE_STORAGE_KEY, paused ? "1" : "0");
  } catch {
    // Storage is unavailable or full: the choice is simply not remembered.
  }
}

export interface PausedFeed {
  paused: boolean;
  /** When the reader paused on this page; null while running, or for a pause restored from storage. */
  pausedSince: Date | null;
  /** When the reader last resumed on this page; null while paused or before any pause. */
  resumedAt: Date | null;
  toggle: () => void;
}

/** Tracks whether the live edit feed is paused, and remembers the choice in localStorage. */
export function usePausedFeed(): PausedFeed {
  const [state, setState] = useState(() => ({
    paused: readStoredPaused(),
    pausedSince: null as Date | null,
    resumedAt: null as Date | null,
  }));

  function toggle() {
    const paused = !state.paused;
    const at = new Date();
    setState({ paused, pausedSince: paused ? at : null, resumedAt: paused ? null : at });
    writeStoredPaused(paused);
  }

  return { ...state, toggle };
}
