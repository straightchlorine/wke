import { useEffect, useRef } from "react";

/** How long a hash link waits for its target to appear before it gives up. */
const HASH_TARGET_WAIT_MS = 15_000;

// Last scroll position per history entry, keyed by the router's entry key (history.state.__TSR_key).
// A hash link pushes a new entry with the same pathname, so a pathname key would overwrite the position of the entry being left.
// The pathname is the fallback until the router has set a key.
const scrollByEntry = new Map<string, number>();
let lastNavWasPopstate = false;

interface HistoryEntryState {
  // The router's own per-entry key name, not ours to rename.
  // oxlint-disable-next-line no-underscore-dangle
  __TSR_key?: string;
}

function hasTsrKey(value: unknown): value is HistoryEntryState {
  return typeof value === "object" && value !== null && "__TSR_key" in value;
}

function currentEntryKey(pathname: string): string {
  const state: unknown = window.history.state;
  // The router's own per-entry key name, not ours to rename.
  // oxlint-disable-next-line no-underscore-dangle
  const key = hasTsrKey(state) ? state.__TSR_key : undefined;
  return typeof key === "string" ? key : pathname;
}

// Capture-phase click and keydown run before a navigation starts, so the position is saved before the new route renders.
// The scroll listener in the hook covers departures that no click or key causes, such as a typed URL.
if (typeof window !== "undefined") {
  const recordScroll = () =>
    scrollByEntry.set(currentEntryKey(window.location.pathname), window.scrollY);
  window.addEventListener("click", recordScroll, { capture: true });
  window.addEventListener("keydown", recordScroll, { capture: true });
  window.addEventListener("popstate", () => {
    lastNavWasPopstate = true;
  });
}

// A web font that loads after the scroll can reflow the page and move the target, so scroll once more when fonts are ready.
// If the fonts were already loaded, the second scroll changes nothing.
function scrollNow(target: HTMLElement): void {
  target.scrollIntoView({ block: "start" });
  document.fonts?.ready?.then(() => target.scrollIntoView({ block: "start" })).catch(() => {});
}

// A dossier section mounts only after its data has loaded, so a hash target may not exist yet.
// A MutationObserver waits for it and fires on the DOM change itself, so nothing has to poll.
function scrollToHash(hash: string): void {
  const id = hash.slice(1);
  if (!id) {
    return;
  }
  const existing = document.getElementById(id);
  if (existing) {
    scrollNow(existing);
    return;
  }
  const observer = new MutationObserver(() => {
    const target = document.getElementById(id);
    if (target) {
      observer.disconnect();
      scrollNow(target);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  // The target may never arrive, for a bad hash or a dossier that fails to build.
  setTimeout(() => observer.disconnect(), HASH_TARGET_WAIT_MS);
}

/**
 * Restores scroll on Back and Forward and scrolls to the URL hash target, leaving plain route changes to the router's `scrollRestoration` option.
 * `settled` is true once the router has finished navigating.
 */
export function useScrollRestoration(pathname: string, hash: string, settled: boolean): void {
  const isFirstRender = useRef(true);
  // The pathname and hash last acted on. The router also goes pending and idle for a change of search params alone,
  // which re-runs the effect below with the same pathname and hash. That is not a new page to scroll.
  const handledLocation = useRef<string | null>(null);

  useEffect(() => {
    function handleScroll() {
      scrollByEntry.set(currentEntryKey(window.location.pathname), window.scrollY);
    }
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!settled) {
      return;
    }
    const location = `${pathname}${hash}`;
    if (!isFirstRender.current && location === handledLocation.current) {
      lastNavWasPopstate = false;
      return;
    }
    handledLocation.current = location;
    if (isFirstRender.current) {
      isFirstRender.current = false;
      // On a direct load with a hash, the browser looks for the target before the route's data has mounted it.
      if (hash) {
        scrollToHash(hash);
      }
      return;
    }
    if (lastNavWasPopstate) {
      lastNavWasPopstate = false;
      const saved = scrollByEntry.get(currentEntryKey(pathname));
      if (saved != null) {
        // Wait one frame so this restore runs after the router's own scroll restoration, which would otherwise win.
        requestAnimationFrame(() => window.scrollTo(0, saved));
      } else if (hash) {
        scrollToHash(hash);
      }
      return;
    }
    // A same-page hash link, or a route change that lands on a hash, scrolls to the hash target.
    if (hash) {
      scrollToHash(hash);
    }
  }, [pathname, hash, settled]);
}
